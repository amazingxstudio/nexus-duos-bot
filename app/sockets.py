import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.socketio_app import sio
from app.security import verify_session_token
from app.cache import set_user_online, set_user_offline
from app.database import AsyncSessionLocal
from app.models import Room, Match, Game, GameKey, RoomStatus, Profile, Friend, User
from app.games.engine.registry import get_game_engine, is_game_implemented
from app.games.engine.match_runner import start_match, handle_game_action, handle_player_disconnect, leave_match
from app.matchmaking import create_room, join_room

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
    await _notify_friends_of_status(user_id, True)


@sio.on("disconnect")
async def disconnect(sid):
    session = await sio.get_session(sid)
    user_id = session.get("user_id") if session else None
    if not user_id:
        return

    await set_user_offline(user_id)
    logger.info("socket disconnected user_id=%s", user_id)
    await _notify_friends_of_status(user_id, False)

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


@sio.on("match:leave")
async def match_leave(sid, data):
    """Player tapped Exit and confirmed. leave_match decides forfeit vs
    void based on whether the opponent is still connected — see its
    docstring in match_runner.py."""
    session = await sio.get_session(sid)
    user_id = session["user_id"]
    match_id = (data or {}).get("match_id")
    if not match_id:
        return

    async with AsyncSessionLocal() as db:
        match = await db.get(Match, match_id)
        if not match or user_id not in (match.player1_id, match.player2_id):
            return
        game = await db.get(Game, match.game_id)

    try:
        engine = get_game_engine(game.key)
    except ValueError:
        return

    await leave_match(engine, match_id, user_id)


@sio.on("turn_nudge")
async def turn_nudge(sid, data):
    """A player is waiting on their rival's turn (Connect Four / Dots and
    Boxes) and tapped the nudge button — relay a one-off buzz to the rival.
    No rate limiting server-side; the frontend enforces its own 3s cooldown
    on the button itself."""
    session = await sio.get_session(sid)
    user_id = session["user_id"]
    match_id = (data or {}).get("match_id")
    if not match_id:
        return

    async with AsyncSessionLocal() as db:
        match = await db.get(Match, match_id)
        if not match or user_id not in (match.player1_id, match.player2_id):
            return
        opponent_id = match.player2_id if match.player1_id == user_id else match.player1_id

    if opponent_id:
        await sio.emit("turn_nudge", {"match_id": match_id, "from_user_id": user_id}, room=f"user:{opponent_id}")


# ---- Presence broadcast to friends -------------------------------------

async def _notify_friends_of_status(user_id: str, online: bool):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Friend).where(Friend.friend_id == user_id))
        watchers = result.scalars().all()
    for w in watchers:
        await sio.emit("friend_status_changed", {"user_id": user_id, "online": online}, room=f"user:{w.user_id}")


# ---- Duel invites (friend list "Invite to Duel" + post-match "Duel Again") --
#
# An invite optionally carries a preset game_key: the inviter picked a
# specific game (or the "Duel Again" rematch reuses the game just played)
# instead of leaving it to the usual Voting phase. None means Voting, same
# as an invite always used to behave. The key travels with the invite
# payload and the accepter's client echoes it straight back on accept —
# no extra server-side state needed — and both ends re-validate it against
# the real game registry before trusting it, so a stale/unknown key just
# quietly falls back to Voting instead of failing the invite.

async def _valid_game_key(db, game_key: str | None):
    """Returns (key, name) for an implemented game, or (None, None) for
    anything missing/unknown/not-yet-built — the safe fallback is Voting."""
    if not game_key:
        return None, None
    try:
        key_enum = GameKey(game_key)
    except ValueError:
        return None, None
    if not is_game_implemented(key_enum):
        return None, None
    game = (await db.execute(select(Game).where(Game.key == key_enum))).scalar_one_or_none()
    if not game:
        return None, None
    return key_enum.value, game.name


@sio.on("invite:send")
async def invite_send(sid, data):
    session = await sio.get_session(sid)
    from_user_id = session["user_id"]
    to_user_id = (data or {}).get("to_user_id")
    if not to_user_id:
        return

    async with AsyncSessionLocal() as db:
        profile = (await db.execute(select(Profile).where(Profile.user_id == from_user_id))).scalar_one_or_none()
        if not profile:
            return
        game_key, game_name = await _valid_game_key(db, (data or {}).get("game_key"))
        await sio.emit(
            "invite:received",
            {
                "from_user_id": from_user_id,
                "from_nickname": profile.nickname,
                "from_player_id": profile.player_id,
                "game_key": game_key,
                "game_name": game_name,
                "is_rematch": bool((data or {}).get("is_rematch")),
            },
            room=f"user:{to_user_id}",
        )


@sio.on("invite:accept")
async def invite_accept(sid, data):
    session = await sio.get_session(sid)
    accepter_id = session["user_id"]
    from_user_id = (data or {}).get("from_user_id")
    if not from_user_id:
        return

    async with AsyncSessionLocal() as db:
        game_key, _ = await _valid_game_key(db, (data or {}).get("game_key"))
        room = await create_room(db, from_user_id, preset_game_key=game_key)
        room, match = await join_room(db, room.code, accepter_id)

    payload = {"room_code": room.code}
    await sio.emit("invite:accepted", payload, room=f"user:{from_user_id}")
    await sio.emit("invite:accepted", payload, room=f"user:{accepter_id}")


@sio.on("invite:decline")
async def invite_decline(sid, data):
    session = await sio.get_session(sid)
    decliner_id = session["user_id"]
    from_user_id = (data or {}).get("from_user_id")
    if not from_user_id:
        return
    await sio.emit("invite:declined", {"by_user_id": decliner_id}, room=f"user:{from_user_id}")
