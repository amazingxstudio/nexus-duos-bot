import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.cache import save_match_state, load_match_state, delete_match_state
from app.database import AsyncSessionLocal
from app.models import Match, Profile, MatchResult, MatchMode, Room, RoomStatus
from app.socketio_app import sio
from app.games.engine.utils import now_ms

logger = logging.getLogger("nexus_duos.engine")

_active_timers: dict[str, asyncio.Task] = {}


async def start_match(engine, match_id: str, room_code: str, player_ids: list[str]) -> dict:
    state = {
        "match_id": match_id,
        "room_code": room_code,
        "game_key": engine.game_key.value,
        "started_at": now_ms(),
        "duration_ms": engine.duration_ms,
        "players": {uid: {"user_id": uid, "connected": True, "score": 0, "finished": False} for uid in player_ids},
        "payload": engine.create_initial_payload(),
        "status": "active",
    }

    engine.on_match_start(state)
    await save_match_state(match_id, state)

    await sio.emit(
        "game_started",
        {
            "match_id": match_id,
            "payload": engine.sanitize_payload_for_client(state["payload"]),
            "duration_ms": state["duration_ms"],
        },
        room=f"room:{room_code}",
    )

    task = asyncio.create_task(_run_timer(engine, match_id, room_code, engine.duration_ms))
    _active_timers[match_id] = task

    return state


async def _run_timer(engine, match_id: str, room_code: str, duration_ms: int):
    remaining = duration_ms
    try:
        while remaining > 0:
            await asyncio.sleep(1)
            remaining -= 1000
            await sio.emit("game_timer_tick", {"remaining_ms": max(remaining, 0)}, room=f"room:{room_code}")
        await finish_match(engine, match_id)
    except asyncio.CancelledError:
        pass


async def handle_game_action(engine, match_id: str, user_id: str, action_type: str, data: dict) -> None:
    state = await load_match_state(match_id)
    if not state or state["status"] != "active":
        return

    try:
        updated = engine.apply_action(state, user_id, action_type, data)
    except ValueError as e:
        logger.warning("Rejected invalid game action: %s", e)
        return

    await save_match_state(match_id, updated)

    await sio.emit(
        "score_updated",
        {"scores": {uid: p["score"] for uid, p in updated["players"].items()}},
        room=f"room:{updated['room_code']}",
    )
    await sio.emit(
        "game_state_updated",
        {"payload": engine.sanitize_payload_for_client(updated["payload"])},
        room=f"room:{updated['room_code']}",
    )

    if engine.should_finish_early(updated):
        await finish_match(engine, match_id)


async def finish_match(engine, match_id: str) -> None:
    state = await load_match_state(match_id)
    if not state or state["status"] == "finished":
        return

    state["status"] = "finished"
    task = _active_timers.pop(match_id, None)
    if task:
        task.cancel()

    result = engine.compute_result(state)
    player_ids = list(result["scores"].keys())
    p1_id = player_ids[0]
    p2_id = player_ids[1] if len(player_ids) > 1 else None

    def _result_for(uid: str) -> MatchResult:
        if not p2_id:
            return MatchResult.WIN
        if result["winner_id"] == uid:
            return MatchResult.WIN
        if result["winner_id"] is None:
            return MatchResult.DRAW
        return MatchResult.LOSS

    async with AsyncSessionLocal() as db:
        match = await db.get(Match, match_id)
        if match:
            match.player1_score = result["scores"].get(p1_id, 0)
            match.player2_score = result["scores"].get(p2_id, 0) if p2_id else 0
            match.player1_result = _result_for(p1_id)
            match.player2_result = _result_for(p2_id) if p2_id else None
            match.winner_id = result["winner_id"]
            match.finished_at = datetime.now(timezone.utc)
            match.duration_ms = now_ms() - state["started_at"]

            if match.mode == MatchMode.RANKED:
                await _update_profile_stats(db, p1_id, match.player1_result, match.player1_score)
                if p2_id:
                    await _update_profile_stats(db, p2_id, match.player2_result, match.player2_score)

            if match.room_id:
                room = await db.get(Room, match.room_id)
                if room:
                    room.status = RoomStatus.FINISHED
                    room.finished_at = datetime.now(timezone.utc)

            await db.commit()

    await delete_match_state(match_id)

    await sio.emit("game_finished", {"match_id": match_id, "result": result}, room=f"room:{state['room_code']}")


async def _update_profile_stats(db, user_id: str, result: MatchResult, score: int) -> None:
    result_row = await db.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result_row.scalar_one_or_none()
    if not profile:
        return
    profile.total_matches += 1
    if result == MatchResult.WIN:
        profile.wins += 1
    elif result == MatchResult.LOSS:
        profile.losses += 1
    elif result == MatchResult.DRAW:
        profile.draws += 1
    profile.total_score += score


async def handle_player_disconnect(match_id: str, user_id: str) -> None:
    state = await load_match_state(match_id)
    if not state:
        return
    if user_id in state["players"]:
        state["players"][user_id]["connected"] = False
    await save_match_state(match_id, state)
