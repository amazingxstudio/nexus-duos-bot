import random
import string
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = "8907138819:AAFaoYPga8s6KqwfSy6z2d0jACa1CA8LZl4"
FIREBASE_URL = "https://nexus-duos-default-rtdb.asia-southeast1.firebasedatabase.app"
WEBAPP_URL = "https://telegram-game-bot-ten.vercel.app/" # မင်းရဲ့ WebApp URL ထည့်ပါ

def generate_room_code():
    return ''.join(random.choices(string.digits, k=5))

def save_to_firebase(path, data):
    requests.put(f"{FIREBASE_URL}/{path}.json", json=data)

def get_from_firebase(path):
    res = requests.get(f"{FIREBASE_URL}/{path}.json")
    return res.json()

async def sync_user_profile(user):
    user_data = get_from_firebase(f"users/{user.id}")
    if not user_data:
        new_profile = {
            "id": user.id,
            "username": user.username or user.first_name,
            "nickname": user.first_name,
            "photo_url": "",
            "show_history_to_all": False,
            "score": 0
        }
        save_to_firebase(f"users/{user.id}", new_profile)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await sync_user_profile(user)
    
    keyboard = [
        [InlineKeyboardButton("🎮 Open Game App", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("🎲 Create Room (Voting)", callback_data="mode_vote")],
        [InlineKeyboardButton("❌ Tic-Tac-Toe Invite", callback_data="mode_game_tictactoe")],
        [InlineKeyboardButton("✂️ Rock-Paper-Scissors Invite", callback_data="mode_game_rps")]
    ]
    
    await update.message.reply_text(
        f"Welcome {user.first_name}! ✅ Profile synced.\nChoose how you want to play:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data
    
    if data.startswith("mode_"):
        game_type = None if data == "mode_vote" else data.replace("mode_game_", "")
        room_code = generate_room_code()
        
        room_data = {
            "p1": user.id,
            "p1_name": user.first_name,
            "p2": None,
            "p2_name": None,
            "specific_game": game_type,
            "status": "waiting",
            "p1_votes": [],
            "p2_votes": []
        }
        save_to_firebase(f"rooms/{room_code}", room_data)
        
        game_str = f"Specific Game: `{game_type}`" if game_type else "Mode: `Voting Mode`"
        await query.edit_message_text(
            f"Room Created! ✅\n\nRoom Code: `{room_code}`\n{game_str}\n\n"
            f"Send this command to another player:\n`/join {room_code}`",
            parse_mode="Markdown"
        )

async def join_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await sync_user_profile(user)
    
    if not context.args:
        await update.message.reply_text("Please provide a Room Code. Example: `/join 12345`", parse_mode="Markdown")
        return
        
    room_code = context.args[0]
    room = get_from_firebase(f"rooms/{room_code}")
    
    if not room:
        await update.message.reply_text("Room not found or expired.")
        return
        
    if room["p1"] == user.id:
        await update.message.reply_text("You are the host of this room.")
        return

    save_to_firebase(f"rooms/{room_code}/p2", user.id)
    save_to_firebase(f"rooms/{room_code}/p2_name", user.first_name)
    save_to_firebase(f"rooms/{room_code}/status", "connected")
    
    app_link = f"{WEBAPP_URL}?room={room_code}"
    keyboard = [[InlineKeyboardButton("🎮 Launch Room Web App", web_app=WebAppInfo(url=app_link))]]
    
    await update.message.reply_text(
        f"Successfully ✅ joined Room `{room_code}`!\nClick below to launch game:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

    try:
        host_id = int(room["p1"])
        await context.bot.send_message(
            chat_id=host_id,
            text=f"Another player ({user.first_name}) joined Room `{room_code}`! Click to launch:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        print(f"Host notification error: {e}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("join", join_room))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("Bot is running...")
    app.run_polling()
    
