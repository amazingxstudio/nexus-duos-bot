from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_auth
from app.models import Room, User, Profile, Game
from app.schemas import JoinRoomRequest, SubmitPicksRequest, SubmitTieBreakRequest
from app.matchmaking import create_room, join_room, submit_vote_picks, submit_tie_break_vote

router = APIRouter()


def _player_out(user: User | None, profile: Profile | None):
    if not user:
        return None
    return {
        "id": user.id,
        "photo_url": user.photo_url,
        "nickname": profile.nickname if profile else None,
        "player_id": profile.player_id if profile else None,
    }


async def _room_response(db: AsyncSession, room: Room) -> dict:
    p1 = await db.get(User, room.player1_id)
    p1_profile = (await db.execute(select(Profile).where(Profile.user_id == room.player1_id))).scalar_one_or_none()

    p2 = await db.get(User, room.player2_id) if room.player2_id else None
    p2_profile = None
    if room.player2_id:
        p2_profile = (await db.execute(select(Profile).where(Profile.user_id == room.player2_id))).scalar_one_or_none()

    game = await db.get(Game, room.game_id) if room.game_id else None

    return {
        "id": room.id,
        "code": room.code,
        "status": room.status.value,
        "player1": _player_out(p1, p1_profile),
        "player2": _player_out(p2, p2_profile),
        "game": {"key": game.key.value, "name": game.name} if game else None,
    }


@router.post("")
async def create_room_route(auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    room = await create_room(db, auth["user_id"])
    return {"room": await _room_response(db, room)}


@router.post("/join")
async def join_room_route(body: JoinRoomRequest, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    try:
        room = await join_room(db, body.code.strip().upper(), auth["user_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"room": await _room_response(db, room)}


@router.get("/{code}")
async def get_room_route(code: str, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Room).where(Room.code == code))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="ROOM_NOT_FOUND")
    return {"room": await _room_response(db, room)}


@router.post("/{room_id}/vote/picks")
async def submit_picks_route(room_id: str, body: SubmitPicksRequest, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    try:
        outcome = await submit_vote_picks(db, room_id, auth["user_id"], body.picks)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return outcome


@router.post("/{room_id}/vote/tiebreak")
async def submit_tiebreak_route(room_id: str, body: SubmitTieBreakRequest, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    try:
        outcome = await submit_tie_break_vote(db, room_id, auth["user_id"], body.game_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return outcome
