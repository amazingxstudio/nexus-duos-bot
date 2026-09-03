from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_auth
from app.models import Room, User, Profile, Game, Match
from app.schemas import JoinRoomRequest, SubmitPicksRequest, SubmitTieBreakRequest
from app.matchmaking import create_room, join_room, submit_vote_picks, submit_tie_break_vote, create_practice_room
from app.capacity import ensure_capacity_available
from app.socketio_app import sio
from app.bot import send_telegram_message, delete_telegram_message

router = APIRouter()


class QuickDuelRequest(BaseModel):
    game_key: str


class PracticeRoomRequest(BaseModel):
    game_key: str
    difficulty: str


def _player_out(user: User | None, profile: Profile | None):
    if not user:
        return None
    return {
        "id": user.id, "photo_url": user.photo_url,
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

    match_result = await db.execute(select(Match).where(Match.room_id == room.id))
    match = match_result.scalar_one_or_none()

    return {
        "id": room.id, "code": room.code, "status": room.status.value,
        "player1": _player_out(p1, p1_profile),
        "player2": _player_out(p2, p2_profile),
        "game": {"key": game.key.value, "name": game.name} if game else None,
        "match_id": match.id if match else None,
    }


@router.post("")
async def create_room_route(auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    # Gate BEFORE creating anything — see app/capacity.py's docstring for
    # why this is checked here (room creation) rather than at match-start.
    try:
        await ensure_capacity_available(db)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    room = await create_room(db, auth["user_id"])
    message_id = await send_telegram_message(
        int(auth["telegram_id"]),
        f"🎮 Room created: <code>{room.code}</code>\n\nTap the code to copy it, then share it with a friend so they can join you in Nexus Duos.",
        parse_mode="HTML",
    )
    if message_id:
        room.telegram_message_id = message_id
        await db.commit()
    return {"room": await _room_response(db, room)}


@router.post("/quick")
async def quick_duel_route(body: QuickDuelRequest, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """Tap-a-game-on-Home flow: creates a room pre-locked to one game — no voting once player2 joins."""
    try:
        await ensure_capacity_available(db)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    room = await create_room(db, auth["user_id"], preset_game_key=body.game_key)
    message_id = await send_telegram_message(
        int(auth["telegram_id"]),
        f"🎮 Room created: <code>{room.code}</code>\n\nTap the code to copy it, then share it with a friend so they can join you in Nexus Duos.",
        parse_mode="HTML",
    )
    if message_id:
        room.telegram_message_id = message_id
        await db.commit()
    return {"room": await _room_response(db, room)}


@router.post("/practice")
async def create_practice_room_route(body: PracticeRoomRequest, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """Practice vs AI: unlike /rooms and /rooms/quick, this never sends a
    'share this code' Telegram DM — there's no second human to invite, the
    room comes back already fully paired with the bot and READY_CHECK'd.
    Still gated by the same capacity check as a real duel: a practice
    match runs its own active-match timer/AI-poll loop just like a ranked
    one does, so it counts against the same concurrency budget."""
    try:
        await ensure_capacity_available(db)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        room, _match = await create_practice_room(db, auth["user_id"], body.game_key, body.difficulty)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"room": await _room_response(db, room)}


@router.post("/join")
async def join_room_route(body: JoinRoomRequest, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    try:
        room, match = await join_room(db, body.code.strip().upper(), auth["user_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # The code just became unusable — it was a one-shot invite for a room
    # that's now full. Clean up the original "Room created" DM in the
    # creator's Telegram chat so it doesn't linger looking like a still-open
    # invite. (Rooms created via in-app invite/rematch never had a DM in the
    # first place, so telegram_message_id is simply None for those — this
    # is a no-op for them.)
    if room.telegram_message_id:
        creator = await db.get(User, room.player1_id)
        if creator:
            await delete_telegram_message(creator.telegram_id, room.telegram_message_id)

    room_out = await _room_response(db, room)
    await sio.emit("room_joined", {"room": room_out}, room=f"room:{room.code}")

    if match:
        game = await db.get(Game, room.game_id)
        await sio.emit(
            "vote:resolved",
            {"game_key": game.key.value, "game_name": game.name, "match_id": match.id},
            room=f"room:{room.code}",
        )
    return {"room": room_out}


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

    room = await db.get(Room, room_id)
    if room:
        if outcome.get("waiting"):
            await sio.emit("vote:player_submitted", {"user_id": auth["user_id"]}, room=f"room:{room.code}")
        elif outcome.get("resolved"):
            await sio.emit("vote:resolved", {"game_key": outcome["game_key"], "game_name": outcome["game_name"], "match_id": outcome["match_id"]}, room=f"room:{room.code}")
        else:
            await sio.emit("vote:tiebreak_required", {"candidates": outcome["candidates"]}, room=f"room:{room.code}")
    return outcome


@router.post("/{room_id}/vote/tiebreak")
async def submit_tiebreak_route(room_id: str, body: SubmitTieBreakRequest, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    try:
        outcome = await submit_tie_break_vote(db, room_id, auth["user_id"], body.game_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    room = await db.get(Room, room_id)
    if room:
        if outcome.get("waiting"):
            await sio.emit("vote:player_submitted", {"user_id": auth["user_id"]}, room=f"room:{room.code}")
        else:
            await sio.emit("vote:resolved", {"game_key": outcome["game_key"], "game_name": outcome["game_name"], "match_id": outcome["match_id"]}, room=f"room:{room.code}")
    return outcome
