from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, GameKey

# The final lineup — all 8 slots are wired here from day one. A game whose
# engine is still a "coming soon" placeholder (see
# app/games/engine/registry.py) stays in this list with its real name; the
# frontend is what decides whether it's selectable yet (see
# lib/games.ts's comingSoon flag), not this table.
GAMES = [
    (GameKey.CONNECT_FOUR, "Connect Four", "Drop discs and connect four in a row before your rival."),
    (GameKey.DOTS_AND_BOXES, "Dots and Boxes", "Claim boxes by drawing the closing line — most boxes wins."),
    (GameKey.QUICK_MATH, "Quick Math", "Same problem, same instant — fastest correct answer wins."),
    (GameKey.TYPING_RACE, "Typing Race", "Same sentence, fastest accurate typist wins."),
    (GameKey.GUESS_THE_WORD, "Guess the Word", "Guess the hidden word from live clues before your rival."),
    (GameKey.MEMORY_RACE, "Memory Race", "Memorize the sequence, reproduce it first."),
    (GameKey.FIND_THE_DIFFERENT, "Find the Different One", "Spot the odd one out before your rival does."),
    (GameKey.WORD_CHAIN, "Word Chain", "Chain valid words by their last letter, beat the clock."),
]


async def seed_games(db: AsyncSession) -> None:
    """Inserts any game that doesn't exist yet, and keeps name/description in
    sync for ones that already do — so this file only ever needs a value
    changed (never a structural edit) if a game's blurb changes."""
    result = await db.execute(select(Game))
    existing = {g.key: g for g in result.scalars().all()}

    for key, name, description in GAMES:
        row = existing.get(key)
        if row is None:
            db.add(Game(key=key, name=name, description=description, is_active=True))
        elif row.name != name or row.description != description:
            row.name = name
            row.description = description

    await db.commit()
