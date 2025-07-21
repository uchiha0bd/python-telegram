import logging
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import httpx
import json
from dotenv import load_dotenv
import os
import signal
import asyncio

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

# Configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DIFY_API_KEY = os.getenv('DIFY_API_KEY')
DIFY_ENDPOINT = "http://botfather.store/v1/chat-messages"

# Conversation storage
user_conversations = defaultdict(dict)
STORAGE_FILE = "conversations.json"

def load_conversations():
    """Load saved conversations from file"""
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE) as f:
                loaded = json.load(f)
                for k, v in loaded.items():
                    user_conversations[k].update(v)
            logger.info("Loaded previous conversations")
        except Exception as e:
            logger.error(f"Error loading conversations: {e}")

def save_conversations():
    """Save conversations to file"""
    try:
        with open(STORAGE_FILE, 'w') as f:
            json.dump({k: v for k, v in user_conversations.items() if v}, f)
    except Exception as e:
        logger.error(f"Error saving conversations: {e}")

async def call_dify_api(payload: dict) -> dict:
    """Make API call to Dify"""
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(DIFY_ENDPOINT, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"API Error: {e.response.text}")
        if e.response.status_code == 404 and "conversation_id" in payload:
            logger.info("Retrying without conversation_id")
            payload.pop("conversation_id")
            return await call_dify_api(payload)
        return {"answer": f"⚠️ API Error: {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        return {"answer": "⚠️ Service unavailable, please try later"}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    await update.message.reply_text("📁 Welcome! Send me a message to start chatting.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    user_id = str(update.effective_user.id)
    
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    payload = {
        "inputs": {},
        "query": update.message.text,
        "response_mode": "blocking",
        "user": user_id
    }
    
    if user_conversations[user_id].get('conversation_id'):
        payload["conversation_id"] = user_conversations[user_id]['conversation_id']
    
    response = await call_dify_api(payload)
    
    if "conversation_id" in response:
        user_conversations[user_id]['conversation_id'] = response["conversation_id"]
    
    await update.message.reply_text(response.get("answer", "🤖 No response received"))

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

def handle_shutdown(signum, frame):
    """Handle shutdown signal"""
    logger.info("Shutting down...")
    save_conversations()
    exit(0)

if __name__ == '__main__':
    # Load previous conversations
    load_conversations()
    
    # Set up signal handler
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # Create and run application
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    logger.info("Bot starting...")
    app.run_polling()