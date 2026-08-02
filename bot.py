import random
import string
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = "8907138819:AAFaoYPga8s6KqwfSy6z2d0jACa1CA8LZl4"
FIREBASE_URL = "https://nexus-duos-default-rtdb.asia-southeast1.firebasedatabase.app"
WEBAPP_URL = "https://nexus-duos-bot.vercel.app/"

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

async def fb_put(path: str, data: dict):
    async with httpx.AsyncClient() as client:
        await client.put(f"{FIREBASE_URL}/{path}.json", json=data)

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
        [InlineKeyboardButton("⚔️ Create Voting Room", callback_data="btn_create_room")]
    ]
    
    welcome_text = (
        f"👋 Welcome {user.first_name}!\n\n"
        "🎮 Use the app to play games, practice vs AI, or invite friends.\n\n"
        "Commands:\n"
        "• /createroom - Create a multiplayer room with Game Voting\n"
        "• /play <game> - Direct game (e.g., /play tictactoe, /play rps)\n"
        "• /join <room_id> - Join a friend's room"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def create_room_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await sync_user_profile(user)
    
    room_id = generate_room_code()
    room_data = {
        "id": room_id,
        "host": str(user.id),
        "hostName": user.first_name,
        "mode": "voting",
        "status": "waiting",
        "createdAt": httpx.QueryParams({".sv": "timestamp"})
    }
    
    await fb_put(f"rooms/{room_id}", room_data)
    
    invite_url = f"{WEBAPP_URL}?room={room_id}"
    keyboard = [[InlineKeyboardButton("🚀 Join & Vote Game", web_app=WebAppInfo(url=invite_url))]]
    
    await update.message.reply_text(
        f"✅ Voting Room Created!\nRoom ID: `{room_id}`\n\nInvite your friend to join!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def play_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await sync_user_profile(user)
    
    if not context.args:
        await update.message.reply_text("⚠️ Please specify a game. Example: `/play tictactoe` or `/play rps`", parse_mode="Markdown")
        return
        
    game_id = context.args[0].lower()
    if game_id not in ["tictactoe", "rps"]:
        await update.message.reply_text("⚠️ Invalid game. Choose `tictactoe` or `rps`.", parse_mode="Markdown")
        return

    room_id = generate_room_code()
    room_data = {
        "id": room_id,
        "host": str(user.id),
        "hostName": user.first_name,
        "mode": "direct",
        "game": game_id,
        "status": "waiting"
    }
    
    await fb_put(f"rooms/{room_id}", room_data)
    
    invite_url = f"{WEBAPP_URL}?room={room_id}&game={game_id}"
    keyboard = [[InlineKeyboardButton(f"🎯 Play {game_id.upper()}", web_app=WebAppInfo(url=invite_url))]]
    
    await update.message.reply_text(
        f"✅ Direct Game Room Created ({game_id.upper()})!\nRoom ID: `{room_id}`\n\nClick below to launch:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def join_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await sync_user_profile(user)
    
    if not context.args:
        await update.message.reply_text("⚠️ Please provide a Room ID. Example: `/join A1B2C3`", parse_mode="Markdown")
        return
        
    room_id = context.args[0].upper()
    room_data = await fb_get(f"rooms/{room_id}")
    
    if not room_data:
        await update.message.reply_text("❌ Room not found or expired.")
        return

    invite_url = f"{WEBAPP_URL}?room={room_id}"
    if room_data.get("game"):
        invite_url += f"&game={room_data.get('game')}"

    keyboard = [[InlineKeyboardButton("🚀 Open Room", web_app=WebAppInfo(url=invite_url))]]
    await update.message.reply_text(f"Joining Room `{room_id}`...", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("createroom", create_room_cmd))
    app.add_handler(CommandHandler("play", play_cmd))
    app.add_handler(CommandHandler("join", join_cmd))
    
    print("Bot is running...")
    app.run_polling()
        
