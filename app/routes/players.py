from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.database import get_db
from app.dependencies import require_auth
from app.models import Profile, User, Friend, UserSettings
from app.cache import is_user_online

router = APIRouter()


class AddFriendRequest(BaseModel):
    player_id: str | None = None
    user_id: str | None = None


class RemoveFriendRequest(BaseModel):
    user_id: str


def _relative_last_seen(dt: datetime | None) -> str:
    """Server-side relative-time formatting so the frontend stays simple —
    "Just now" / "5m ago" / "2h ago" / "3d ago", falling back to
    "Last seen recently" for anything older than ~7 days (or missing)."""
    if not dt:
        return "Last seen recently"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = (datetime.now(timezone.utc) - dt).total_seconds()
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    if seconds < 7 * 86400:
        return f"{int(seconds // 86400)}d ago"
    return "Last seen recently"


async def _card(db, profile: Profile, user: User, online: bool) -> dict:
    """Builds a player card, respecting the TARGET user's own presence
    settings: show_online_status is a master toggle (off = nobody sees
    real online/offline or last-seen, always "Last seen recently"), and
    show_exact_last_seen (only relevant when the master toggle is on)
    controls whether their own last-seen time is exact or vague."""
    target_settings = (await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )).scalar_one_or_none()
    show_online_status = target_settings.show_online_status if target_settings else True
    show_exact_last_seen = target_settings.show_exact_last_seen if target_settings else True

    if not show_online_status:
        return {
            "user_id": user.id,
            "nickname": profile.nickname,
            "player_id": profile.player_id,
            "photo_url": user.photo_url,
            "online": False,
            "last_seen_at": None,
            "last_seen_label": "Last seen recently",
        }

    return {
        "user_id": user.id,
        "nickname": profile.nickname,
        "player_id": profile.player_id,
        "photo_url": user.photo_url,
        "online": online,
        "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
        "last_seen_label": _relative_last_seen(user.last_seen_at) if show_exact_last_seen else "Last seen recently",
    }


@router.get("/search")
async def search_players(query: str, auth=Depends(require_auth), db=Depends(get_db)):
    query = query.strip().upper()
    if len(query) < 3:
        return {"players": []}

    result = await db.execute(select(Profile).where(Profile.player_id.like(f"%{query}%")).limit(10))
    profiles = [p for p in result.scalars().all() if p.user_id != auth["user_id"]]

    out = []
    for p in profiles:
        user = await db.get(User, p.user_id)
        if user:
            out.append(await _card(db, p, user, await is_user_online(user.id)))
    return {"players": out}


@router.post("/friends")
async def add_friend(body: AddFriendRequest, auth=Depends(require_auth), db=Depends(get_db)):
    if body.user_id:
        target_profile = (await db.execute(select(Profile).where(Profile.user_id == body.user_id))).scalar_one_or_none()
    elif body.player_id:
        target_profile = (await db.execute(select(Profile).where(Profile.player_id == body.player_id.strip().upper()))).scalar_one_or_none()
    else:
        raise HTTPException(status_code=400, detail="MISSING_IDENTIFIER")
    if not target_profile:
        raise HTTPException(status_code=404, detail="PLAYER_NOT_FOUND")
    if target_profile.user_id == auth["user_id"]:
        raise HTTPException(status_code=400, detail="CANNOT_ADD_YOURSELF")

    existing = (await db.execute(
        select(Friend).where(Friend.user_id == auth["user_id"], Friend.friend_id == target_profile.user_id)
    )).scalar_one_or_none()
    if existing:
        return {"ok": True, "already_friends": True}

    db.add(Friend(user_id=auth["user_id"], friend_id=target_profile.user_id))
    await db.commit()
    return {"ok": True, "already_friends": False}


@router.get("/friends")
async def list_friends(auth=Depends(require_auth), db=Depends(get_db)):
    result = await db.execute(select(Friend).where(Friend.user_id == auth["user_id"]))
    friend_rows = result.scalars().all()

    out = []
    for row in friend_rows:
        user = await db.get(User, row.friend_id)
        if not user:
            continue
        profile = (await db.execute(select(Profile).where(Profile.user_id == row.friend_id))).scalar_one_or_none()
        if not profile:
            continue
        out.append(await _card(db, profile, user, await is_user_online(user.id)))
    return {"friends": out}


@router.get("/friends/status")
async def friend_status(user_id: str, auth=Depends(require_auth), db=Depends(get_db)):
    existing = (await db.execute(
        select(Friend).where(Friend.user_id == auth["user_id"], Friend.friend_id == user_id)
    )).scalar_one_or_none()
    return {"is_friend": existing is not None}


@router.post("/friends/remove")
async def remove_friend(body: RemoveFriendRequest, auth=Depends(require_auth), db=Depends(get_db)):
    existing = (await db.execute(
        select(Friend).where(Friend.user_id == auth["user_id"], Friend.friend_id == body.user_id)
    )).scalar_one_or_none()
    if not existing:
        return {"ok": True, "removed": False}

    await db.delete(existing)
    await db.commit()
    return {"ok": True, "removed": True}
