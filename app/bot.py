import asyncio
import html
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from telegram.error import TelegramError

from sqlalchemy import or_, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Game, Match, Profile, User, UserSettings
from app.room_code import generate_player_id

logger = logging.getLogger("nexus_duos.bot")

# Module-level singleton — created once, imported everywhere. Building a
# second Application elsewhere would start a second polling loop and cause
# Telegram's "409 Conflict: terminated by other getUpdates request" error.
bot_application: Application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()


async def bootstrap_user_profile(tg_user) -> None:
    is_new_user = False
    new_user_snapshot: dict | None = None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.telegram_id == tg_user.id))
        user = result.scalar_one_or_none()

        # Checked by numeric id, never username — usernames can change or be
        # removed. Applied on every /start, not just creation, in case
        # CREATOR_TELEGRAM_ID is set/changed after this account already exists.
        is_creator_account = settings.CREATOR_TELEGRAM_ID is not None and tg_user.id == settings.CREATOR_TELEGRAM_ID

        if user:
            user.username = tg_user.username
            user.first_name = tg_user.first_name
            user.last_name = tg_user.last_name
            user.language_code = tg_user.language_code
            if is_creator_account:
                user.is_creator = True
        else:
            is_new_user = True
            user = User(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                language_code=tg_user.language_code,
                is_creator=is_creator_account,
            )
            db.add(user)
            await db.flush()

            player_id = generate_player_id()
            db.add(Profile(user_id=user.id, nickname=tg_user.username or tg_user.first_name, player_id=player_id))
            db.add(UserSettings(user_id=user.id))

            new_user_snapshot = {
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "player_id": player_id,
            }

        await db.commit()

    # Fired after the session above is closed — never hold a DB session
    # open across an outgoing network call.
    if is_new_user and new_user_snapshot:
        await notify_creator_of_new_signup(new_user_snapshot)


async def notify_creator_of_new_signup(snapshot: dict) -> None:
    """DMs whoever currently holds is_creator about a brand-new signup.
    Skips silently if no creator is currently set."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.is_creator.is_(True)))
        creator = result.scalars().first()

    if not creator:
        return

    handle = f"@{snapshot['username']}" if snapshot["username"] else snapshot["first_name"]
    # parse_mode="HTML" + <code>...</code> makes Telegram render the id as a
    # monospace span — tapping/holding it copies just that value, no manual
    # selection needed. handle/player_id are escaped since they can contain
    # arbitrary user-controlled text (first_name), which could otherwise
    # break HTML parsing; telegram_id is always numeric so it's safe as-is.
    text = (
        "🆕 New Nexus Duos signup\n"
        f"Name: {html.escape(handle)}\n"
        f"Telegram ID: <code>{snapshot['telegram_id']}</code>\n"
        f"Player ID: <code>{html.escape(snapshot['player_id'])}</code>"
    )
    await send_telegram_message(creator.telegram_id, text, parse_mode="HTML")


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


# ---- Creator / admin system ----

async def require_creator(update: Update) -> User | None:
    """Looks up the calling Telegram user's row and returns it only if
    is_creator is True — otherwise returns None so callers can silently
    no-op or reply "Not authorized"."""
    tg_user = update.effective_user
    if not tg_user:
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.telegram_id == tg_user.id))
        user = result.scalar_one_or_none()
        return user if user and user.is_creator else None


PLAYERS_PAGE_SIZE = 8


async def _render_players_page(page: int) -> tuple[str, InlineKeyboardMarkup]:
    offset = max(page, 0) * PLAYERS_PAGE_SIZE
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User, Profile)
            .join(Profile, Profile.user_id == User.id)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(PLAYERS_PAGE_SIZE + 1)  # one extra row just to know if a next page exists
        )
        rows = result.all()

    has_next = len(rows) > PLAYERS_PAGE_SIZE
    rows = rows[:PLAYERS_PAGE_SIZE]

    keyboard: list[list[InlineKeyboardButton]] = []
    for user, profile in rows:
        label = f"@{user.username}" if user.username else user.first_name
        keyboard.append([InlineKeyboardButton(label, callback_data=f"admin_player:{user.id}:{page}")])

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ Prev", callback_data=f"admin_players_page:{page - 1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton("Next ▶", callback_data=f"admin_players_page:{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    text = f"👥 Registered players — page {page + 1}" if rows else "No players found."
    return text, InlineKeyboardMarkup(keyboard)


async def _render_player_detail(user_id: str, back_page: int) -> tuple[str, InlineKeyboardMarkup]:
    back_button = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Back to list", callback_data=f"admin_players_page:{back_page}")]])

    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if not user:
            return "Player not found.", back_button

        profile = (await db.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one_or_none()

        matches = list((await db.execute(
            select(Match).where(Match.finished_at.is_not(None))
            .where(or_(Match.player1_id == user.id, Match.player2_id == user.id))
            .order_by(Match.finished_at.desc()).limit(10)
        )).scalars().all())

        # Resolve every distinct user referenced across these matches (both
        # sides) in one query — the creator view always shows real Telegram
        # identities and ignores every player's show_history_to_all setting.
        other_ids = {m.player1_id for m in matches} | {m.player2_id for m in matches if m.player2_id}
        other_ids.discard(user.id)
        identities: dict[str, User] = {user.id: user}
        if other_ids:
            for u in (await db.execute(select(User).where(User.id.in_(other_ids)))).scalars().all():
                identities[u.id] = u

        game_ids = {m.game_id for m in matches}
        games_by_id = {g.id: g for g in (await db.execute(select(Game).where(Game.id.in_(game_ids)))).scalars().all()} if game_ids else {}

    def display_name(uid: str | None) -> str:
        if not uid:
            return "AI"
        u = identities.get(uid)
        if not u:
            return "Unknown"
        return f"@{u.username}" if u.username else u.first_name

    if user.username:
        account = f"@{user.username}"
    else:
        account = user.first_name + (f" {user.last_name}" if user.last_name else "")

    signed_up = user.created_at.strftime("%b %d, %Y %H:%M UTC") if user.created_at else "Unknown"
    last_seen = user.last_seen_at.strftime("%b %d, %Y %H:%M UTC") if user.last_seen_at else "Unknown"

    lines = [
        f"👤 {account}",
        f"Player ID: {profile.player_id if profile else '—'}",
        f"Signed up: {signed_up}",
        f"Last seen: {last_seen}",
        "",
        "Recent matches:",
    ]
    if matches:
        for m in matches:
            game = games_by_id.get(m.game_id)
            game_name = game.name if game else "Unknown"
            p1_name = display_name(m.player1_id)
            p2_name = display_name(m.player2_id)
            lines.append(f"{p1_name} {m.player1_score} — {m.player2_score} {p2_name} ({game_name})")
    else:
        lines.append("No finished matches yet.")

    return "\n".join(lines), back_button


async def players_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    creator = await require_creator(update)
    if not creator:
        await update.message.reply_text("Not authorized.")
        return

    text, markup = await _render_players_page(0)
    await update.message.reply_text(text, reply_markup=markup)


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return

    creator = await require_creator(update)
    if not creator:
        await query.answer("Not authorized.", show_alert=True)
        return

    await query.answer()
    data = query.data

    try:
        if data.startswith("admin_players_page:"):
            page = int(data.split(":", 1)[1])
            text, markup = await _render_players_page(page)
            await query.edit_message_text(text, reply_markup=markup)
        elif data.startswith("admin_player:"):
            _, user_id, page_str = data.split(":", 2)
            text, markup = await _render_player_detail(user_id, int(page_str))
            await query.edit_message_text(text, reply_markup=markup)
    except TelegramError:
        # e.g. "message is not modified" from a double-tap — harmless.
        logger.warning("Admin callback edit failed for %s", data)
    except Exception:
        logger.exception("Failed to handle admin callback %s", data)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    creator = await require_creator(update)
    if not creator:
        await update.message.reply_text("Not authorized.")
        return

    message_text = " ".join(context.args).strip() if context.args else ""
    if not message_text:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    async with AsyncSessionLocal() as db:
        telegram_ids = [row[0] for row in (await db.execute(select(User.telegram_id))).all()]

    total = len(telegram_ids)
    sent = 0
    batch_size = 20
    for i in range(0, total, batch_size):
        batch = telegram_ids[i:i + batch_size]
        for telegram_id in batch:
            # send_telegram_message already wraps the call in try/except —
            # one blocked/deactivated user never aborts the rest.
            message_id = await send_telegram_message(telegram_id, message_text)
            if message_id is not None:
                sent += 1
        if i + batch_size < total:
            await asyncio.sleep(1)

    await update.message.reply_text(f"Sent to {sent} of {total} users.")


bot_application.add_handler(CommandHandler("start", start_command))
bot_application.add_handler(CommandHandler("players", players_command))
bot_application.add_handler(CommandHandler("broadcast", broadcast_command))
bot_application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern=r"^admin_(players_page|player):"))


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
