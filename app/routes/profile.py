from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import require_auth
from app.models import User, Profile, UserSettings, Friend, ProfileVisit
from app.schemas import UpdateNicknameRequest
from app.cache import invalidate_user_cache, cache_public_profile, get_cached_public_profile, invalidate_public_profile_cache

router = APIRouter()


@router.get("/me")
async def get_my_profile(auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    # Deliberately never cached — a player landing here right after a
    # match (see the frontend's profile page + RoomSync's game_finished
    # listener) expects their just-updated wins/losses immediately, not up
    # to PUBLIC_PROFILE_CACHE_TTL_SECONDS later. See get_public_profile
    # below for the cached path used for OTHER players' profiles.
    user = await db.get(User, auth["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    profile = (await db.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one_or_none()
    settings = (await db.execute(select(UserSettings).where(UserSettings.user_id == user.id))).scalar_one_or_none()
    recent_visitors = await _recent_visitors(db, user.id) if profile else []
    return {
        "id": user.id, "telegram_id": str(user.telegram_id), "first_name": user.first_name,
        "username": user.username, "photo_url": user.photo_url,
        "profile": _profile_out(profile), "settings": _settings_out(settings),
        "recent_visitors": recent_visitors,
    }


@router.patch("/me/nickname")
async def update_nickname(body: UpdateNicknameRequest, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    profile = (await db.execute(select(Profile).where(Profile.user_id == auth["user_id"]))).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="PROFILE_NOT_FOUND")
    profile.nickname = body.nickname
    await db.commit()
    await invalidate_user_cache(auth["telegram_id"])
    # The public-profile cache is keyed by player_id and holds the
    # nickname, so a rename must invalidate it or other players would see
    # the stale name for up to PUBLIC_PROFILE_CACHE_TTL_SECONDS.
    await invalidate_public_profile_cache(profile.player_id)
    return {"profile": _profile_out(profile)}


@router.get("/leaderboard")
async def get_leaderboard(auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    # Registered above the dynamic /{player_id} route below so "leaderboard"
    # is never swallowed as a player_id lookup.
    result = await db.execute(select(Profile).order_by(Profile.total_score.desc()).limit(50))
    profiles = result.scalars().all()
    return {
        "players": [
            {"nickname": p.nickname, "player_id": p.player_id, "total_score": p.total_score, "wins": p.wins}
            for p in profiles
        ]
    }


@router.get("/{player_id}")
async def get_public_profile(player_id: str, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    profile = (await db.execute(select(Profile).where(Profile.player_id == player_id))).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="PROFILE_NOT_FOUND")

    # Recording the visit always happens on the live request, never from
    # cache — see cache.py's PUBLIC_PROFILE_CACHE_TTL_SECONDS docstring for
    # why a few minutes of staleness on the CACHED response is fine, but
    # the visit itself (used by the profile OWNER's own /me view, which is
    # never cached) needs to land immediately.
    if auth["user_id"] != profile.user_id:
        await _record_profile_visit(db, profile.user_id, auth["user_id"])

    cached = await get_cached_public_profile(player_id)
    if cached is not None:
        cached["is_friend"] = (await db.execute(
            select(Friend).where(Friend.user_id == auth["user_id"], Friend.friend_id == profile.user_id)
        )).scalar_one_or_none() is not None
        return cached

    user = await db.get(User, profile.user_id)
    settings = (await db.execute(select(UserSettings).where(UserSettings.user_id == profile.user_id))).scalar_one_or_none()
    win_rate = round((profile.wins / profile.total_matches) * 100) if profile.total_matches > 0 else 0
    recent_visitors = await _recent_visitors(db, profile.user_id)

    out = {
        "nickname": profile.nickname, "player_id": profile.player_id,
        "photo_url": user.photo_url if user else None,
        "total_matches": profile.total_matches, "wins": profile.wins, "losses": profile.losses,
        "draws": profile.draws, "win_rate": win_rate, "total_score": profile.total_score,
        "history_visible": settings.show_history_to_all if settings else True,
        "recent_visitors": recent_visitors,
    }
    await cache_public_profile(player_id, out)

    already_friends = (await db.execute(
        select(Friend).where(Friend.user_id == auth["user_id"], Friend.friend_id == profile.user_id)
    )).scalar_one_or_none() is not None
    return {**out, "is_friend": already_friends}


def _profile_out(profile):
    if not profile:
        return None
    return {
        "id": profile.id, "nickname": profile.nickname, "player_id": profile.player_id,
        "total_matches": profile.total_matches, "wins": profile.wins, "losses": profile.losses,
        "draws": profile.draws, "total_score": profile.total_score,
    }


def _settings_out(settings):
    if not settings:
        return None
    return {
        "show_history_to_all": settings.show_history_to_all,
        "sound_enabled": settings.sound_enabled, "haptics_enabled": settings.haptics_enabled,
    }


# ---- Profile visitors (spec D.13) ---------------------------------------

async def _record_profile_visit(db: AsyncSession, owner_id: str, visitor_id: str) -> None:
    """Upserts one row per (owner, visitor) pair — a repeat visit just
    bumps visited_at instead of stacking up duplicate rows, which is what
    makes "3 most recent visitors" a plain ORDER BY on this table."""
    existing = (await db.execute(
        select(ProfileVisit).where(ProfileVisit.profile_owner_id == owner_id, ProfileVisit.visitor_id == visitor_id)
    )).scalar_one_or_none()
    if existing:
        existing.visited_at = datetime.now(timezone.utc)
    else:
        db.add(ProfileVisit(profile_owner_id=owner_id, visitor_id=visitor_id))
    await db.commit()


async def _recent_visitors(db: AsyncSession, owner_id: str, limit: int = 3) -> list[dict]:
    """Top `limit` most-recent visitors, each as a small clickable card —
    the frontend links each one to /profile/{player_id}, which is what
    makes browsing visitor-of-a-visitor-of-a-visitor work for free: it's
    just the same profile route again, recursively."""
    result = await db.execute(
        select(ProfileVisit).where(ProfileVisit.profile_owner_id == owner_id)
        .order_by(ProfileVisit.visited_at.desc()).limit(limit)
    )
    visits = result.scalars().all()
    if not visits:
        return []

    visitor_ids = [v.visitor_id for v in visits]
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(visitor_ids)))).scalars().all()}
    profiles = {p.user_id: p for p in (await db.execute(select(Profile).where(Profile.user_id.in_(visitor_ids)))).scalars().all()}

    out = []
    for v in visits:
        user = users.get(v.visitor_id)
        profile = profiles.get(v.visitor_id)
        if user and profile:
            out.append({"nickname": profile.nickname, "player_id": profile.player_id, "photo_url": user.photo_url})
    return out
