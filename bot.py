import random
import string
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = "8907138819:AAFaoYPga8s6KqwfSy6z2d0jACa1CA8LZl4"
FIREBASE_URL = "https://nexus-duos-default-rtdb.asia-southeast1.firebasedatabase.app"

def generate_room_code():
    # Generate 5-digit numeric code
    return ''.join(random.choices(string.digits, k=5))

def save_to_firebase(path, data):
    url = f"{FIREBASE_URL}/{path}.json"
    requests.put(url, json=data)

def get_from_firebase(path):
    url = f"{FIREBASE_URL}/{path}.json"
    response = requests.get(url)
    return response.json()

def get_keypad_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("1", callback_data="kp_1"),
            InlineKeyboardButton("2", callback_data="kp_2"),
            InlineKeyboardButton("3", callback_data="kp_3")
        ],
        [
            InlineKeyboardButton("4", callback_data="kp_4"),
            InlineKeyboardButton("5", callback_data="kp_5"),
            InlineKeyboardButton("6", callback_data="kp_6")
        ],
        [
            InlineKeyboardButton("7", callback_data="kp_7"),
            InlineKeyboardButton("8", callback_data="kp_8"),
            InlineKeyboardButton("9", callback_data="kp_9")
        ],
        [
            InlineKeyboardButton("⌫ Clear", callback_data="kp_del"),
            InlineKeyboardButton("0", callback_data="kp_0"),
            InlineKeyboardButton("✓ Submit", callback_data="kp_sub")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Use /createroom to create a new game room,\n"
        "or use /join to join an existing room."
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

async def process_join_logic(user, room_code, send_reply_func):
    room = get_from_firebase(f"rooms/{room_code}")
    
    if not room:
        await send_reply_func("Room not found or expired.")
        return False
        
    if room["p1"] == user.id:
        await send_reply_func("You are the host of this room.")
        return False

    save_to_firebase(f"rooms/{room_code}/p2", user.id)
    save_to_firebase(f"rooms/{room_code}/p2_name", user.first_name)
    
    keyboard = [
        [InlineKeyboardButton("Ready!", callback_data=f"ready_{room_code}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_reply_func(
        f"Successfully joined Room `{room_code}`!\n\n"
        f"Host: *{room['p1_name']}*\n\n"
        f"Please click Ready button below when you are prepared.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

    return room

async def join_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Option 1: Direct join (/join 12345)
    if context.args:
        room_code = context.args[0]
        async def send_msg(text, **kwargs):
            await update.message.reply_text(text, **kwargs)
            
        room = await process_join_logic(user, room_code, send_msg)
        if room:
            try:
                host_id = int(room["p1"])
                keyboard = [[InlineKeyboardButton("Ready!", callback_data=f"ready_{room_code}")]]
                await context.bot.send_message(
                    chat_id=host_id,
                    text=f"Player 2 (*{user.first_name}*) has joined your Room `{room_code}`!\n\nPlease click Ready button below.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Failed to notify host: {e}")
        return

    # Option 2: Keypad UI (/join)
    context.user_data["join_code"] = ""
    display_code = "_ _ _ _ _"
    
    await update.message.reply_text(
        f"Enter 5-digit Room Code:\n\n`{display_code}`",
        reply_markup=get_keypad_keyboard(),
        parse_mode="Markdown"
    )

async def handle_keypad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data.replace("kp_", "")
    user = query.from_user
    
    current_code = context.user_data.get("join_code", "")
    
    if action.isdigit():
        if len(current_code) < 5:
            current_code += action
            context.user_data["join_code"] = current_code
    elif action == "del":
        current_code = current_code[:-1]
        context.user_data["join_code"] = current_code
    elif action == "sub":
        if len(current_code) != 5:
            await query.answer("Please enter all 5 digits first!", show_alert=True)
            return
            
        await query.answer()
        
        async def edit_query_msg(text, **kwargs):
            await query.edit_message_text(text, **kwargs)
            
        room = await process_join_logic(user, current_code, edit_query_msg)
        if room:
            try:
                host_id = int(room["p1"])
                keyboard = [[InlineKeyboardButton("Ready!", callback_data=f"ready_{current_code}")]]
                await context.bot.send_message(
                    chat_id=host_id,
                    text=f"Player 2 (*{user.first_name}*) has joined your Room `{current_code}`!\n\nPlease click Ready button below.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Failed to notify host: {e}")
        return

    await query.answer()
    
    code_chars = list(current_code)
    display_list = code_chars + ["_"] * (5 - len(code_chars))
    display_code = " ".join(display_list)
    
    text = f"Enter 5-digit Room Code:\n\n`{display_code}`"
    
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=get_keypad_keyboard(),
            parse_mode="Markdown"
        )
    except Exception:
        pass

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
        
        finish_msg = "Both players are ready!\n\nGame setup complete in Firebase."
        
        await query.edit_message_text(finish_msg)
        
        other_user_id = int(room["p2"]) if user_id == int(room["p1"]) else int(room["p1"])
        try:
            await context.bot.send_message(chat_id=other_user_id, text=finish_msg)
        except Exception as e:
            print(f"Failed to notify other player: {e}")
    else:
        await query.edit_message_text(
            "You are READY! Waiting for the other player to click Ready..."
        )

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("createroom", create_room))
    app.add_handler(CommandHandler("join", join_room))
    app.add_handler(CallbackQueryHandler(handle_keypad, pattern="^kp_"))
    app.add_handler(CallbackQueryHandler(handle_ready, pattern="^ready_"))
    
    print("Bot with Firebase is running...")
    app.run_polling()

