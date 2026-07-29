import random
import string
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = "8907138819:AAFaoYPga8s6KqwfSy6z2d0jACa1CA8LZl4"
FIREBASE_URL = "https://nexus-duos-default-rtdb.asia-southeast1.firebasedatabase.app"

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def save_to_firebase(path, data):
    url = f"{FIREBASE_URL}/{path}.json"
    requests.put(url, json=data)

def get_from_firebase(path):
    url = f"{FIREBASE_URL}/{path}.json"
    response = requests.get(url)
    return response.json()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Use /createroom to create a new game room,\n"
        "or use /join <ROOM_CODE> to join an existing room."
    )

async def create_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    room_code = generate_room_code()
    
    room_data = {
        "p1": user.id,
        "p1_name": user.first_name,
        "p2": None,
        "p2_name": None,
        "p1_ready": False,
        "p2_ready": False,
        "status": "waiting"
    }
    
    save_to_firebase(f"rooms/{room_code}", room_data)
    
    await update.message.reply_text(
        f"Room created successfully!\n\n"
        f"Room Code: `{room_code}`\n\n"
        f"Share this code and ask player 2 to type `/join {room_code}`",
        parse_mode="Markdown"
    )

async def join_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text("Please provide a Room Code. Example: `/join ABC123`", parse_mode="Markdown")
        return
        
    room_code = context.args[0].upper()
    room = get_from_firebase(f"rooms/{room_code}")
    
    if not room:
        await update.message.reply_text("Room not found or expired.")
        return
        
    if room["p1"] == user.id:
        await update.message.reply_text("You are the host of this room.")
        return

    save_to_firebase(f"rooms/{room_code}/p2", user.id)
    save_to_firebase(f"rooms/{room_code}/p2_name", user.first_name)
    
    keyboard = [
        [InlineKeyboardButton("Ready!", callback_data=f"ready_{room_code}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"{room['p1_name']} and {user.first_name} are connected!\n\n"
        f"Both players please click the Ready button.", 
        reply_markup=reply_markup
    )

async def handle_ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    room_code = query.data.split("_")[1]
    
    room = get_from_firebase(f"rooms/{room_code}")
    
    if not room:
        await query.edit_message_text("Room expired.")
        return

    if user_id == room["p1"]:
        save_to_firebase(f"rooms/{room_code}/p1_ready", True)
        room["p1_ready"] = True
    elif user_id == room["p2"]:
        save_to_firebase(f"rooms/{room_code}/p2_ready", True)
        room["p2_ready"] = True

    if room["p1_ready"] and room["p2_ready"]:
        save_to_firebase(f"rooms/{room_code}/status", "ready")
        await query.edit_message_text(
            "Both players are ready!\n\n"
            "Data saved to database successfully."
        )
    else:
        await query.message.reply_text(f"{query.from_user.first_name} is ready. Waiting for the other player...")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("createroom", create_room))
    app.add_handler(CommandHandler("join", join_room))
    app.add_handler(CallbackQueryHandler(handle_ready, pattern="^ready_"))
    
    print("Bot with Firebase is running...")
    app.run_polling()
  
