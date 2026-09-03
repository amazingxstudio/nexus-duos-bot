"""Friend-to-friend direct messages — Friends list "Message" button, spec
section D.14/15. Deliberately small: no read receipts, no pagination
beyond the hard cap below — this is a lightweight "say hi / call them over
for a duel" channel, not a full chat product.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, or_, and_, delete

from app.models import DirectMessage, Friend

# Only the most recent HISTORY_LIMIT messages are kept PER PAIR — older
# ones are deleted the moment a new one pushes the pair over the cap (see
# send_message below). RETENTION_HOURS is a second, independent rule: any
# message older than this, regardless of how many exist for the pair, is
# swept up by cleanup.py's periodic pass — see prune_expired_messages.
HISTORY_LIMIT = 20
RETENTION_HOURS = 24


def _pair_filter(user_a: str, user_b: str):
    return or_(
        and_(DirectMessage.sender_id == user_a, DirectMessage.receiver_id == user_b),
        and_(DirectMessage.sender_id == user_b, DirectMessage.receiver_id == user_a),
    )


async def are_friends(db, user_a: str, user_b: str) -> bool:
    """Friendship here isn't necessarily symmetric in the DB (each side
    adds their own Friend row), so this only checks the direction that
    matters for the caller — see sockets.py/routes/messages.py, which
    always call this as are_friends(me, them) to gate MY ability to
    message THEM."""
    row = (await db.execute(
        select(Friend).where(Friend.user_id == user_a, Friend.friend_id == user_b)
    )).scalar_one_or_none()
    return row is not None


async def get_conversation(db, user_a: str, user_b: str, limit: int = HISTORY_LIMIT) -> list[DirectMessage]:
    result = await db.execute(
        select(DirectMessage).where(_pair_filter(user_a, user_b)).order_by(DirectMessage.created_at.desc()).limit(limit)
    )
    return list(reversed(result.scalars().all()))  # oldest → newest for display


async def send_message(db, sender_id: str, receiver_id: str, content: str) -> DirectMessage:
    message = DirectMessage(sender_id=sender_id, receiver_id=receiver_id, content=content)
    db.add(message)
    await db.commit()
    await db.refresh(message)

    # Enforce the per-pair cap immediately rather than waiting for the
    # periodic cleanup pass — a fast back-and-forth shouldn't be able to
    # grow the table unbounded between sweeps.
    overflow = await db.execute(
        select(DirectMessage.id).where(_pair_filter(sender_id, receiver_id))
        .order_by(DirectMessage.created_at.desc()).offset(HISTORY_LIMIT)
    )
    overflow_ids = [row[0] for row in overflow.all()]
    if overflow_ids:
        await db.execute(delete(DirectMessage).where(DirectMessage.id.in_(overflow_ids)))
        await db.commit()

    return message


async def prune_expired_messages(db) -> int:
    """Deletes any message older than RETENTION_HOURS, independent of the
    per-pair cap above. Called periodically by app/cleanup.py — commits
    its own delete and returns the row count removed (for logging)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)
    result = await db.execute(delete(DirectMessage).where(DirectMessage.created_at < cutoff))
    await db.commit()
    return result.rowcount or 0
