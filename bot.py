import os
import sqlite3
import aiohttp
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Database setup
def init_db():
    conn = sqlite3.connect('chat_history.db')
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
    return conn, cursor

conn, cursor = init_db()

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
    
    # Call Hugging Face API (free)
    API_URL = "https://api-inference.huggingface.co/models/HuggingFaceH4/zephyr-7b-beta"
    
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": 300,
                    "temperature": 0.7,
                    "do_sample": True
                }
            }
            
            async with session.post(API_URL, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    ai_reply = result[0]['generated_text'].strip()
                else:
                    ai_reply = "I'm here! What would you like to talk about?"
                    
    except Exception as e:
        ai_reply = "Hello! I'm ready to chat. What's on your mind?"
    
    # Save to database
    save_message(user_id, "user", user_input)
    save_message(user_id, "assistant", ai_reply)
    
    return ai_reply

# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Hello! I'm your AI assistant with memory!")

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
    await update.message.reply_text("🗑️ Chat history cleared!")

def main():
    try:
        application = Application.builder().token(TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("clear", clear_history))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("✅ Bot starting...")
        application.run_polling()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Check your TOKEN and internet connection")

if __name__ == "__main__":
    main()
