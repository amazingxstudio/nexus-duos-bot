from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Profile, UserSettings
from app.games.ai.difficulty import AIDifficulty
from app.games.ai.bots import AI_BOT_TELEGRAM_IDS, AI_BOT_DISPLAY, register_bot


async def seed_ai_bots(db: AsyncSession) -> None:
    """Ensures the 3 Practice-vs-AI bot accounts (Easy/Normal/Pro) exist —
    inserting whichever ones are missing — and registers each one's real
    user id in app.games.ai.bots for the rest of the process's lifetime.
    Idempotent and additive, same spirit as seed_games: safe to run on
    every boot, never touches a row that already exists beyond re-reading
    its id.
    """
    for difficulty in AIDifficulty:
        telegram_id = AI_BOT_TELEGRAM_IDS[difficulty]
        display = AI_BOT_DISPLAY[difficulty]

        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=telegram_id,
                username=None,
                first_name=display["nickname"],
                is_creator=False,
            )
            db.add(user)
            await db.flush()  # need user.id before the Profile/Settings rows below

            db.add(Profile(user_id=user.id, nickname=display["nickname"], player_id=display["player_id"]))
            # show_online_status defaults True but the bot never opens a
            # socket connection, so it simply always reads as offline —
            # nothing to turn off here.
            db.add(UserSettings(user_id=user.id))

        register_bot(difficulty, user.id)

    await db.commit()
