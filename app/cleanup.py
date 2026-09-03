"""Periodic, non-per-user cleanup — run on a timer by
app/background_tasks.py, unlike app/history_cleanup.py's prune_old_matches
(which runs once per participant right after their match finishes). Keeps
Neon storage from growing unbounded on the free tier — spec section C.11.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.models import Room, RoomStatus
from app.messaging import prune_expired_messages

logger = logging.getLogger("nexus_duos.cleanup")


async def prune_stale_rooms(db) -> int:
    """A room that's been sitting in WAITING_FOR_PLAYER / VOTING /
    READY_CHECK for longer than STALE_ROOM_HOURS was abandoned mid-flow —
    the creator never got a second player, voting never resolved, a
    player closed the app before the ready-check completed, etc. Marking
    it ABANDONED (rather than deleting the row outright) keeps it out of
    app/capacity.py's active-match count while still leaving the row
    around. IN_PROGRESS rooms are never touched here — a live match ending
    is games/engine/match_runner.py's job, not this sweep's."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.STALE_ROOM_HOURS)
    result = await db.execute(
        select(Room).where(
            Room.status.in_((RoomStatus.WAITING_FOR_PLAYER, RoomStatus.VOTING, RoomStatus.READY_CHECK)),
            Room.created_at < cutoff,
        )
    )
    stale_rooms = list(result.scalars().all())
    for room in stale_rooms:
        room.status = RoomStatus.ABANDONED
        room.finished_at = datetime.now(timezone.utc)
    if stale_rooms:
        await db.commit()
    return len(stale_rooms)


async def run_cleanup_pass(session_factory) -> None:
    """One full sweep — a fresh, short-lived DB session per step (rather
    than one long-held session for the whole pass) so a slow/failing step
    never holds a connection open across the other one. Each step is
    independently try/excepted so one failing sweep never blocks the
    other."""
    async with session_factory() as db:
        try:
            n_rooms = await prune_stale_rooms(db)
            if n_rooms:
                logger.info("Cleanup: marked %d stale room(s) ABANDONED", n_rooms)
        except Exception:
            logger.exception("Cleanup: stale-room sweep failed")

    async with session_factory() as db:
        try:
            n_messages = await prune_expired_messages(db)
            if n_messages:
                logger.info("Cleanup: deleted %d expired direct message(s)", n_messages)
        except Exception:
            logger.exception("Cleanup: expired-message sweep failed")
