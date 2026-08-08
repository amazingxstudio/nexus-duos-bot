from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, GameKey

GAMES = [
    (GameKey.CYBER_DUEL, "Cyber Duel", "Reaction + accuracy battle with live combos."),
    (GameKey.NEON_CHESS, "Neon Chess Duel", "Fast tactical mini strategy board game."),
    (GameKey.CODE_BREAKER, "Code Breaker", "Crack the hidden sequence before your rival."),
    (GameKey.ARENA_CARDS, "Arena Cards", "Energy-based strategy card battle."),
    (GameKey.MEMORY_WARFARE, "Memory Warfare", "Head-to-head memory matching with combo multipliers."),
    (GameKey.SPEED_TYPING, "Speed Typing Battle", "Same sentence, fastest accurate typist wins."),
    (GameKey.TOWER_CONTROL, "Tower Control", "Capture zones and manage resources in real time."),
    (GameKey.PUZZLE_ARENA, "Puzzle Arena", "Solve the same generated puzzle — speed decides."),
]


async def seed_games(db: AsyncSession) -> None:
    result = await db.execute(select(Game))
    existing = {g.key for g in result.scalars().all()}

    for key, name, description in GAMES:
        if key not in existing:
            db.add(Game(key=key, name=name, description=description, is_active=True))

    await db.commit()
