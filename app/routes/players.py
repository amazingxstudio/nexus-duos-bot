from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.database import get_db
from app.dependencies import require_auth
from app.models import Profile, User, Friend
from app.cache import is_user_online

router = APIRouter()


class AddFriendRequest(BaseModel):
    player_id: str | None = None
    user_id: str | None = None


def _card(profile: Profile, user: User, online: bool) -> dict:
    return {
        "user_id": user.id,
        "nickname": profile.nickname,
        "player_id": profile.player_id,
        "photo_url": user.photo_url,
        "online": online,
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
            out.append(_card(p, user, await is_user_online(user.id)))
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
        out.append(_card(profile, user, await is_user_online(user.id)))
    return {"friends": out}
