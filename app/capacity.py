"""Concurrent-match capacity gate — spec section C.10.

Render's free tier (0.1 CPU / 512MB), Neon (100 CU-hr/month), and Upstash
(500K commands/month) can only sustain a small, fixed number of matches
running at once before something on the free tier tips over. This gates
at the moment a new room is actually requested — routes/rooms.py's
create/quick-duel routes, and sockets.py's invite_accept (which also
creates a room under the hood for an accepted invite or rematch) — rather
than at match-start, which would be too late: voting, ready-check, and
the room's DB row would already exist by then.

"Active" is deliberately everything that isn't FINISHED/ABANDONED — a room
sitting in WAITING_FOR_PLAYER still holds a live Telegram DM and a room
row, VOTING/READY_CHECK hold an open room:{code} socket channel, and
IN_PROGRESS is the actual gameplay. All of them consume the same shared
capacity; only IN_PROGRESS is the expensive part, but there's no cheap way
to weight them differently, so this counts them all equally.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Room, RoomStatus

_INACTIVE_STATUSES = (RoomStatus.FINISHED, RoomStatus.ABANDONED)


async def active_match_count(db: AsyncSession) -> int:
    return await db.scalar(
        select(func.count()).select_from(Room).where(Room.status.not_in(_INACTIVE_STATUSES))
    ) or 0


async def ensure_capacity_available(db: AsyncSession) -> None:
    """Raises ValueError("SERVER_FULL") once the configured concurrent-
    match limit is reached. Callers turn this into whatever error shape
    fits their transport — an HTTPException for REST (routes/rooms.py) or
    an emitted event for sockets (sockets.py's invite_accept)."""
    if await active_match_count(db) >= settings.MAX_CONCURRENT_MATCHES:
        raise ValueError("SERVER_FULL")
