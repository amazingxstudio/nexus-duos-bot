import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import User, Profile, UserSettings
from app.room_code import generate_player_id

logger = logging.getLogger("nexus_duos.bot")


async def bootstrap_user_profile(tg_user) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.telegram_id == tg_user.id))
        user = result.scalar_one_or_none()

        if user:
            user.username = tg_user.username
            user.first_name = tg_user.first_name
            user.last_name = tg_user.last_name
            user.language_code = tg_user.language_code
        else:
            user = User(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                language_code=tg_user.language_code,
            )
            db.add(user)
            await db.flush()  # get user.id before creating child rows

            db.add(Profile(user_id=user.id, nickname=tg_user.username or tg_user.first_name, player_id=generate_player_id()))
            db.add(UserSettings(user_id=user.id))

        await db.commit()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if not tg_user:
        return

    try:
        await bootstrap_user_profile(tg_user)
    except Exception:
        logger.exception("Failed to bootstrap user profile on /start")

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🎮 Open Nexus Duos", web_app=WebAppInfo(url=settings.TELEGRAM_WEBAPP_URL))]]
    )
    await update.message.reply_text(
        f"Welcome to Nexus Duos, {tg_user.first_name}! ⚡\n\nChallenge a friend to a real-time duel.",
        reply_markup=keyboard,
    )


def build_bot_application() -> Application:
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    return application
