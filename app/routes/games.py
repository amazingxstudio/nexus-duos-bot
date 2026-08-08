from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Game

router = APIRouter()


@router.get("")
async def list_games(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Game).where(Game.is_active == True))
    games = result.scalars().all()
    return {"games": [{"key": g.key.value, "name": g.name, "description": g.description} for g in games]}
