import os
import sqlite3
import aiohttp
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()

# Config
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_API_KEY = os.getenv("HF_API_KEY", "")  # Optional for some models
MODEL_NAME = "HuggingFaceH4/zephyr-7b-beta"  # Free model

# Database setup (same as before)
conn = sqlite3.connect('chat_history.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        user_id INTEGER,
        role TEXT,
        content TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()

def save_message(user_id, role, content):
    cursor.execute(
        "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content)
    )
    conn.commit()

def load_history(user_id, limit=10):
    cursor.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, limit)
    )
    return cursor.fetchall()

async def generate_response(user_id, user_input):
    history = load_history(user_id)
    
    # Build conversation context
    conversation = ""
    for role, content in reversed(history):
        conversation += f"{role}: {content}\n"
    
    # Create prompt
    prompt = f"""<|system|>
You are a helpful AI assistant that remembers conversation history.
Continue the conversation naturally.

Previous conversation:
{conversation}</s>
<|user|>
{user_input}</s>
<|assistant|>
"""
    
    # Call Hugging Face API
    async with aiohttp.ClientSession() as session:
        headers = {
            "Authorization": f"Bearer {HF_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 500,
                "temperature": 0.7,
                "do_sample": True,
                "return_full_text": False
            }
        }
        
        try:
            async with session.post(
                f"https://api-inference.huggingface.co/models/{MODEL_NAME}",
                headers=headers,
                json=payload
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    ai_reply = result[0]['generated_text']
                else:
                    ai_reply = "Sorry, I'm having trouble responding right now."
                    
        except Exception as e:
            ai_reply = f"Error: {str(e)}"
    
    # Save to database
    save_message(user_id, "user", user_input)
    save_message(user_id, "assistant", ai_reply)
    
    return ai_reply

# Telegram handlers (same as before)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hey! I'm your free AI assistant with memory! 🚀")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text
    
    await update.message.chat.send_action(action="typing")
    response = await generate_response(user_id, user_input)
    await update.message.reply_text(response)

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    await update.message.reply_text("History cleared! 🧹")

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Free AI Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
