import random
import string
import time
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = "8907138819:AAFaoYPga8s6KqwfSy6z2d0jACa1CA8LZl4"
FIREBASE_URL = "https://nexus-duos-default-rtdb.asia-southeast1.firebasedatabase.app"
WEBAPP_URL = "https://nexus-duos-bot.vercel.app/"

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

async def fb_put(path: str, data: dict):
    async with httpx.AsyncClient() as client:
        await client.put(f"{FIREBASE_URL}/{path}.json", json=data)

async def fb_patch(path: str, data: dict):
    async with httpx.AsyncClient() as client:
        await client.patch(f"{FIREBASE_URL}/{path}.json", json=data)

async def fb_get(path: str):
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{FIREBASE_URL}/{path}.json")
        return res.json()

async def sync_user_profile(user):
    user_id = str(user.id)
    user_data = await fb_get(f"users/{user_id}")
    if not user_data:
        new_profile = {
            "id": user_id,
            "username": user.username or user.first_name,
            "nickname": user.first_name,
            "photo_url": "",
            "showHistory": False,
            "score": 0
        }
        await fb_put(f"users/{user_id}", new_profile)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await sync_user_profile(user)
    
    keyboard = [
        [InlineKeyboardButton("🎮 Open Game Hub", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("🎲 Create Room (Voting)", callback_data="mode_vote")],
        [InlineKeyboardButton("❌ Tic-Tac-Toe Invite", callback_data="mode_game_tictactoe")],
        [InlineKeyboardButton("✂️ Rock-Paper-Scissors Invite", callback_data="mode_game_rps")]
    ]
    
    welcome_text = (
        f"Welcome <b>{user.first_name}</b>! ✅ Profile synced.\n\n"
        "Choose how you want to play or use commands:\n"
        "• /createroom - Create a multiplayer voting room\n"
        "• /play &lt;game&gt; - Direct game room (e.g. /play tictactoe)\n"
        "• Tap any <b>/join_ROOMCODE</b> link to join a room directly"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def create_room_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await sync_user_profile(user)
    await create_and_send_room(update, context, user, None)

async def play_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await sync_user_profile(user)
    
    if not context.args:
        await update.message.reply_text("Please specify a game. Example: <code>/play tictactoe</code>", parse_mode="HTML")
        return
        
    game_id = context.args[0].lower()
    if game_id not in ["tictactoe", "rps"]:
        await update.message.reply_text("Invalid game. Choose <code>tictactoe</code> or <code>rps</code>.", parse_mode="HTML")
        return

    await create_and_send_room(update, context, user, game_id)

async def create_and_send_room(update: Update, context: ContextTypes.DEFAULT_TYPE, user, game_type):
    try:
        room_code = generate_room_code()
        user_id_str = str(user.id)
        
        # Web App (index.html) အသစ်နှင့် အံဝင်ခွင်ကျဖြစ်စေမည့် Data Fields များ
        room_data = {
            "id": room_code,
            "host": user_id_str,
            "hostName": user.first_name,
            "guest": None,
            "guestName": None,
            "mode": "direct" if game_type else "voting",
            "game": game_type,
            "status": "waiting",
            "createdAt": int(time.time() * 1000)
        }
        await fb_put(f"rooms/{room_code}", room_data)
        
        game_str = f"Game: <b>{game_type.upper()}</b>" if game_type else "Mode: <b>Voting Mode</b>"
        
        invite_url = f"{WEBAPP_URL}?room={room_code}"
        if game_type:
            invite_url += f"&game={game_type}"

        keyboard = [[InlineKeyboardButton("🚀 Launch Room Web App", web_app=WebAppInfo(url=invite_url))]]
        
        msg_text = (
            f"Room Created! ✅\n\nRoom Code: <code>{room_code}</code>\n{game_str}\n\n"
            f"Click link below to join directly:\n/join_{room_code}"
        )

        if update.callback_query:
            await update.callback_query.edit_message_text(
                msg_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                msg_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
    except Exception as e:
        print(f"Error in create_and_send_room: {e}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data
    
    await sync_user_profile(user)
    
    if data in ["btn_create_room", "mode_vote"]:
        await create_and_send_room(update, context, user, None)
    elif data.startswith("mode_game_"):
        game_type = data.replace("mode_game_", "")
        await create_and_send_room(update, context, user, game_type)

async def process_join(update: Update, context: ContextTypes.DEFAULT_TYPE, room_code: str):
    user = update.effective_user
    await sync_user_profile(user)
    
    room = await fb_get(f"rooms/{room_code}")
    
    if not room:
        await update.message.reply_text("Room not found or expired.")
        return
        
    host_id_str = str(room.get("host"))
    if host_id_str == str(user.id):
        await update.message.reply_text("You are the host of this room.")
        return

    # Web App (index.html) အသစ်နှင့် အံဝင်ခွင်ကျဖြစ်စေမည့် Data Fields များ
    user_id_str = str(user.id)
    update_payload = {
        "guest": user_id_str,
        "guestName": user.first_name,
        "status": "connected"
    }
    await fb_patch(f"rooms/{room_code}", update_payload)
    
    invite_url = f"{WEBAPP_URL}?room={room_code}"
    game = room.get("game")
    if game:
        invite_url += f"&game={game}"
        
    keyboard = [[InlineKeyboardButton("🎮 Launch Room Web App", web_app=WebAppInfo(url=invite_url))]]
    
    await update.message.reply_text(
        f"Successfully ✅ joined Room <code>{room_code}</code>!\nClick below to launch game:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

    try:
        host_id = int(host_id_str)
        await context.bot.send_message(
            chat_id=host_id,
            text=f"Another player ({user.first_name}) joined Room <code>{room_code}</code>! Click to launch:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Host notification error: {e}")

async def join_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a Room Code. Example: <code>/join A1B2C3</code>", parse_mode="HTML")
        return
    room_code = context.args[0].upper()
    await process_join(update, context, room_code)

async def join_underscore_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "_" in text:
        parts = text.split("_", 1)
        if len(parts) > 1 and parts[1]:
            room_code = parts[1].split()[0].upper()
            await process_join(update, context, room_code)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("createroom", create_room_cmd))
    app.add_handler(CommandHandler("play", play_cmd))
    app.add_handler(CommandHandler("join", join_cmd))
    app.add_handler(MessageHandler(filters.Regex(r"^/join_"), join_underscore_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("Bot is running...")
    app.run_polling)
