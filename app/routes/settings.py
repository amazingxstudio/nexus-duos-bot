from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import require_auth
from app.models import UserSettings

router = APIRouter()


class UpdateSettingsRequest(BaseModel):
    show_history_to_all: bool | None = None
    sound_enabled: bool | None = None
    haptics_enabled: bool | None = None


@router.get("")
async def get_settings(auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    settings = (await db.execute(select(UserSettings).where(UserSettings.user_id == auth["user_id"]))).scalar_one_or_none()
    if not settings:
        raise HTTPException(status_code=404, detail="SETTINGS_NOT_FOUND")
    return {"settings": _out(settings)}


@router.patch("")
async def update_settings(body: UpdateSettingsRequest, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    settings = (await db.execute(select(UserSettings).where(UserSettings.user_id == auth["user_id"]))).scalar_one_or_none()
    if not settings:
        raise HTTPException(status_code=404, detail="SETTINGS_NOT_FOUND")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)
    await db.commit()
    return {"settings": _out(settings)}


def _out(settings):
    return {
        "show_history_to_all": settings.show_history_to_all,
        "sound_enabled": settings.sound_enabled, "haptics_enabled": settings.haptics_enabled,
    }
