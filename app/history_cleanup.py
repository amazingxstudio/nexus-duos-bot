from sqlalchemy import select, func, or_

from app.models import Match

HISTORY_LIMIT = 10


async def prune_old_matches(db, user_id: str, keep: int = HISTORY_LIMIT) -> None:
    """Keeps only a user's most recent `keep` finished matches, deleting
    older ones. A Match row is shared by both players, so a row is only
    actually deleted once it's beyond *both* players' most-recent-`keep`
    cutoff — otherwise the other player would lose it from their own
    history before they'd even reached the limit themselves. Call this once
    per participant right after a match finishes; it commits its own
    deletes.
    """
    result = await db.execute(
        select(Match)
        .where(Match.finished_at.is_not(None))
        .where(or_(Match.player1_id == user_id, Match.player2_id == user_id))
        .order_by(Match.finished_at.desc())
    )
    matches = list(result.scalars().all())
    if len(matches) <= keep:
        return

    changed = False
    for m in matches[keep:]:
        other_id = m.player2_id if m.player1_id == user_id else m.player1_id
        if other_id:
            other_newer_count = await db.scalar(
                select(func.count())
                .select_from(Match)
                .where(Match.finished_at.is_not(None))
                .where(Match.finished_at > m.finished_at)
                .where(or_(Match.player1_id == other_id, Match.player2_id == other_id))
            )
            if other_newer_count < keep:
                continue  # the other player still needs this row in their own most-recent-N
        await db.delete(m)
        changed = True

    if changed:
        await db.commit()
