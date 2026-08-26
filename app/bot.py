import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import TelegramError

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import User, Profile, UserSettings
from app.room_code import generate_player_id

logger = logging.getLogger("nexus_duos.bot")

# Module-level singleton — created once, imported everywhere. Building a
# second Application elsewhere would start a second polling loop and cause
# Telegram's "409 Conflict: terminated by other getUpdates request" error.
bot_application: Application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()


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
            await db.flush()

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


bot_application.add_handler(CommandHandler("start", start_command))


def build_bot_application() -> Application:
    """Kept for backward compatibility — returns the same singleton."""
    return bot_application


async def send_telegram_message(telegram_id: int, text: str, parse_mode: str | None = None) -> int | None:
    """Lets the web app (REST routes, sockets) push a DM through the bot —
    e.g. sending a freshly-created room code back to its creator.

    parse_mode="HTML" lets the caller wrap part of the text in <code>...</code>
    so Telegram renders it as a monospace, tap-to-copy span (tapping/holding a
    <code> span in Telegram shows "Copy" for just that text, rather than the
    whole message).

    Returns the sent message's id (so a caller can delete it again later —
    see delete_telegram_message), or None if sending failed."""
    try:
        msg = await bot_application.bot.send_message(chat_id=telegram_id, text=text, parse_mode=parse_mode)
        return msg.message_id
    except TelegramError:
        logger.exception("Failed to send Telegram message to %s", telegram_id)
        return None


async def delete_telegram_message(telegram_id: int, message_id: int) -> None:
    """Removes a message the bot previously sent. Used the instant a room
    code stops being usable (someone joined, so it can't be used to join
    again) to clean up the original "Room created" DM — so a player's chat
    with the bot doesn't fill up with dead, already-used codes.

    Failure here (message already gone, chat blocked, message too old,
    etc.) is never allowed to break the join flow that triggered it — it's
    swallowed and just logged."""
    try:
        await bot_application.bot.delete_message(chat_id=telegram_id, message_id=message_id)
    except TelegramError:
        logger.warning("Could not delete Telegram message %s for %s", message_id, telegram_id)
