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
        f"Share this code with Player 2 and ask them to type:\n`/join {room_code}`\n\n"
        f"Waiting for Player 2 to join...",
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
    
    # Message to Player 2
    await update.message.reply_text(
        f"Successfully joined Room `{room_code}`!\n\n"
        f"Host: {room['p1_name']}\n\n"
        f"Please click Ready button below when you are prepared.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

    # Send notification & Ready button to Player 1 (Host)
    try:
        await context.bot.send_message(
            chat_id=room["p1"],
            text=f"🎮 Player 2 ({user.first_name}) has joined your Room `{room_code}`!\n\nPlease click Ready button below.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Failed to notify host: {e}")

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
        
        finish_msg = "🎉 Both players are ready!\n\nGame setup complete in Firebase."
        
        # Update clicking player's UI
        await query.edit_message_text(finish_msg)
        
        # Notify the other player as well
        other_user_id = room["p2"] if user_id == room["p1"] else room["p1"]
        try:
            await context.bot.send_message(chat_id=other_user_id, text=finish_msg)
        except Exception as e:
            print(f"Failed to notify other player: {e}")
    else:
        await query.edit_message_text(
            f"You are READY! ⏳ Waiting for the other player to click Ready..."
        )

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("createroom", create_room))
    app.add_handler(CommandHandler("join", join_room))
    app.add_handler(CallbackQueryHandler(handle_ready, pattern="^ready_"))
    
    print("Bot with Firebase is running...")
    app.run_polling)
