import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.socketio_app import sio
from app.security import verify_session_token
from app.cache import set_user_online, set_user_offline
from app.database import AsyncSessionLocal
from app.models import Room, Match, Game, RoomStatus
from app.games.engine.registry import get_game_engine
from app.games.engine.match_runner import start_match, handle_game_action, handle_player_disconnect

logger = logging.getLogger("nexus_duos.sockets")


@sio.on("connect")
async def connect(sid, environ, auth):
    token = (auth or {}).get("token")
    if not token:
        raise ConnectionRefusedError("UNAUTHENTICATED")

    payload = verify_session_token(token)
    if not payload:
        raise ConnectionRefusedError("INVALID_SESSION")

    user_id = payload["userId"]
    await sio.save_session(sid, {"user_id": user_id, "telegram_id": payload["telegramId"]})
    await set_user_online(user_id, sid)
    await sio.enter_room(sid, f"user:{user_id}")
    logger.info("socket connected user_id=%s sid=%s", user_id, sid)


@sio.on("disconnect")
async def disconnect(sid):
    session = await sio.get_session(sid)
    user_id = session.get("user_id") if session else None
    if not user_id:
        return

    await set_user_offline(user_id)
    logger.info("socket disconnected user_id=%s", user_id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Match)
            .where(Match.finished_at.is_(None))
            .where((Match.player1_id == user_id) | (Match.player2_id == user_id))
            .order_by(Match.started_at.desc())
        )
        active_match = result.scalars().first()

    if active_match:
        await handle_player_disconnect(active_match.id, user_id)
        opponent_id = active_match.player2_id if active_match.player1_id == user_id else active_match.player1_id
        if opponent_id:
            await sio.emit("opponent_disconnected", {"match_id": active_match.id}, room=f"user:{opponent_id}")


@sio.on("room:join_channel")
async def room_join_channel(sid, data):
    room_code = (data or {}).get("room_code")
    if room_code:
        await sio.enter_room(sid, f"room:{room_code}")


@sio.on("player_ready")
async def player_ready(sid, data):
    session = await sio.get_session(sid)
    user_id = session["user_id"]
    room_id = (data or {}).get("room_id")

    async with AsyncSessionLocal() as db:
        room = await db.get(Room, room_id)
    if not room:
        return

    await sio.emit("player_ready", {"user_id": user_id}, room=f"room:{room.code}")


@sio.on("game_started")
async def game_started(sid, data):
    room_id = (data or {}).get("room_id")

    async with AsyncSessionLocal() as db:
        room = await db.get(Room, room_id)
        if not room:
            return

        room.status = RoomStatus.IN_PROGRESS
        room.started_at = datetime.now(timezone.utc)
        await db.commit()

        match_result = await db.execute(select(Match).where(Match.room_id == room_id))
        match = match_result.scalar_one_or_none()
        game = await db.get(Game, room.game_id) if room.game_id else None

    if not match or not game:
        return

    try:
        engine = get_game_engine(game.key)
    except ValueError:
        logger.error("No engine registered for game_key=%s", game.key)
        await sio.emit("game_start_failed", {"reason": "GAME_NOT_AVAILABLE"}, room=f"room:{room.code}")
        return

    player_ids = [room.player1_id] + ([room.player2_id] if room.player2_id else [])
    await start_match(engine, match.id, room.code, player_ids)


@sio.on("game_action")
async def game_action(sid, data):
    session = await sio.get_session(sid)
    user_id = session["user_id"]

    match_id = (data or {}).get("match_id")
    action_type = (data or {}).get("type")
    action_data = (data or {}).get("data") or {}

    async with AsyncSessionLocal() as db:
        match = await db.get(Match, match_id)
        if not match or user_id not in (match.player1_id, match.player2_id):
            return
        game = await db.get(Game, match.game_id)

    try:
        engine = get_game_engine(game.key)
    except ValueError:
        return

    await handle_game_action(engine, match_id, user_id, action_type, action_data)
