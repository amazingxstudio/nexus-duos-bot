from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import require_auth
from app.models import User, Profile, UserSettings
from app.schemas import UpdateNicknameRequest
from app.cache import invalidate_user_cache

router = APIRouter()


@router.get("/me")
async def get_my_profile(auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, auth["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    profile = (await db.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one_or_none()
    settings = (await db.execute(select(UserSettings).where(UserSettings.user_id == user.id))).scalar_one_or_none()
    return {
        "id": user.id, "telegram_id": str(user.telegram_id), "first_name": user.first_name,
        "username": user.username, "photo_url": user.photo_url,
        "profile": _profile_out(profile), "settings": _settings_out(settings),
    }


@router.patch("/me/nickname")
async def update_nickname(body: UpdateNicknameRequest, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    profile = (await db.execute(select(Profile).where(Profile.user_id == auth["user_id"]))).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="PROFILE_NOT_FOUND")
    profile.nickname = body.nickname
    await db.commit()
    await invalidate_user_cache(auth["telegram_id"])
    return {"profile": _profile_out(profile)}


@router.get("/{player_id}")
async def get_public_profile(player_id: str, db: AsyncSession = Depends(get_db)):
    profile = (await db.execute(select(Profile).where(Profile.player_id == player_id))).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="PROFILE_NOT_FOUND")
    user = await db.get(User, profile.user_id)
    settings = (await db.execute(select(UserSettings).where(UserSettings.user_id == profile.user_id))).scalar_one_or_none()
    win_rate = round((profile.wins / profile.total_matches) * 100) if profile.total_matches > 0 else 0
    return {
        "nickname": profile.nickname, "player_id": profile.player_id,
        "photo_url": user.photo_url if user else None,
        "total_matches": profile.total_matches, "wins": profile.wins, "losses": profile.losses,
        "draws": profile.draws, "win_rate": win_rate, "total_score": profile.total_score,
        "history_visible": settings.show_history_to_all if settings else True,
    }


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
