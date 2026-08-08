from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, Profile, UserSettings
from app.schemas import TelegramLoginRequest, AuthResponse, UserOut, ProfileOut, SettingsOut
from app.telegram_auth import verify_telegram_init_data
from app.security import issue_session_token
from app.room_code import generate_player_id
from app.cache import cache_user_profile

router = APIRouter()


@router.post("/telegram", response_model=AuthResponse)
async def telegram_login(body: TelegramLoginRequest, db: AsyncSession = Depends(get_db)):
    verified = verify_telegram_init_data(body.init_data)
    if not verified:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_TELEGRAM_SIGNATURE")

    tg_user = verified["user"]
    telegram_id = int(tg_user["id"])

    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if user:
        user.username = tg_user.get("username")
        user.first_name = tg_user["first_name"]
        user.last_name = tg_user.get("last_name")
        user.photo_url = tg_user.get("photo_url")
        user.language_code = tg_user.get("language_code")
    else:
        user = User(
            telegram_id=telegram_id,
            username=tg_user.get("username"),
            first_name=tg_user["first_name"],
            last_name=tg_user.get("last_name"),
            photo_url=tg_user.get("photo_url"),
            language_code=tg_user.get("language_code"),
        )
        db.add(user)
        await db.flush()

        profile = Profile(user_id=user.id, nickname=tg_user.get("username") or tg_user["first_name"], player_id=generate_player_id())
        settings_row = UserSettings(user_id=user.id)
        db.add(profile)
        db.add(settings_row)

    await db.commit()
    await db.refresh(user)

    result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = result.scalar_one()
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    settings_row = result.scalar_one()

    token = issue_session_token(user.id, str(telegram_id))

    await cache_user_profile(str(telegram_id), {"id": user.id, "nickname": profile.nickname, "player_id": profile.player_id})

    return AuthResponse(
        token=token,
        user=UserOut(
            id=user.id,
            telegram_id=str(telegram_id),
            first_name=user.first_name,
            username=user.username,
            photo_url=user.photo_url,
            profile=ProfileOut.model_validate(profile),
            settings=SettingsOut.model_validate(settings_row),
        ),
    )


@router.post("/logout")
async def logout():
    return {"ok": True}
