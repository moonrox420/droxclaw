from telegram import Update
from telegram.ext import ContextTypes
import os

ALLOWED_USERS = set(map(int, os.getenv("ALLOWED_USER_IDS", "").split(","))) if os.getenv("ALLOWED_USER_IDS") else set()

async def authenticate_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is authorized to use the bot"""
    if not ALLOWED_USERS:
        return True  # No restrictions if not configured
    
    user_id = update.effective_user.id
    return user_id in ALLOWED_USERS

def auth_required(func):
    """Decorator to require authentication for handlers"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await authenticate_user(update, context):
            await update.message.reply_text("Access denied. You are not authorized to use this bot.")
            return
        return await func(update, context)
    return wrapper

# Apply to your handlers:
# @auth_required
# async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
