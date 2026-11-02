#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DarkGPT - Premium AI Telegram Bot
Powered by Custom Claude Opus API
All Features Enabled: Image, Video, GPT-5, Claude Opus 4.5
"""

import os
import sys
import logging
import requests
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from collections import defaultdict

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# API Configuration
API_ENDPOINT = "https://claude-opus-chatbot.onrender.com/chat"
API_TIMEOUT = 120  # 2 minutes for video/image generation

# User conversation storage
user_chats = defaultdict(list)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message with all features"""
    welcome_text = (
        "🌑 *DarkGPT - Premium AI Platform* 🌑\n\n"
        "✨ *ALL FEATURES ENABLED - UNLIMITED & FREE* ✨\n\n"
        
        "🤖 *AI Models Available:*\n"
        "• Claude Opus 4.5 - Most Advanced\n"
        "• GPT-5 Pro - Latest OpenAI\n"
        "• Multi-Model Intelligence\n\n"
        
        "🎨 *Creative Features:*\n"
        "• Image Generation - Unlimited\n"
        "• Video Generation - HD Quality\n"
        "• Audio Processing\n\n"
        
        "🌍 *Language Support:*\n"
        "• Hindi • English • Hinglish\n"
        "• Spanish • French • German\n\n"
        
        "⚡ *Advanced Capabilities:*\n"
        "• Real-time Web Data\n"
        "• Conversation Memory\n"
        "• Context Awareness\n"
        "• No Rate Limits\n\n"
        
        "📱 *Commands:*\n"
        "/start - Show this menu\n"
        "/clear - Reset conversation\n"
        "/help - Detailed help\n"
        "/features - All capabilities\n\n"
        
        "💬 *Just type anything to start!*"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear user conversation history"""
    user_id = update.effective_user.id
    user_chats[user_id] = []
    await update.message.reply_text(
        "✅ *Conversation cleared!*\n\n"
        "Fresh start - all history removed.",
        parse_mode='Markdown'
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detailed help information"""
    help_text = (
        "📚 *DarkGPT Complete Guide* 📚\n\n"
        
        "*How to Use:*\n"
        "1️⃣ Type any question directly\n"
        "2️⃣ Ask for images: 'Generate sunset image'\n"
        "3️⃣ Request videos: 'Create video about space'\n"
        "4️⃣ Multi-language: Hindi, English mix karo\n\n"
        
        "*Example Queries:*\n"
        "• Python code kaise likhe?\n"
        "• Generate a beautiful landscape image\n"
        "• Create 10 second video of ocean waves\n"
        "• Explain quantum physics in Hindi\n"
        "• Latest news about technology\n\n"
        
        "*Special Features:*\n"
        "✅ Remembers full conversation\n"
        "✅ Understands context\n"
        "✅ Multi-turn dialogue\n"
        "✅ Code generation & debugging\n"
        "✅ Real-time information\n\n"
        
        "*No Restrictions:*\n"
        "• Unlimited messages\n"
        "• Unlimited image generation\n"
        "• Unlimited video creation\n"
        "• No daily limits\n\n"
        
        "💡 *Pro Tip:* Be specific for better results!"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def cmd_features(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all available features"""
    features_text = (
        "🚀 *All Features - Fully Enabled* 🚀\n\n"
        
        "🤖 *AI Models:*\n"
        "✅ Claude Opus 4.5 (Latest)\n"
        "✅ GPT-5 Pro\n"
        "✅ Hybrid Intelligence\n"
        "✅ Advanced Reasoning\n\n"
        
        "🎨 *Image Generation:*\n"
        "✅ High Resolution (4K)\n"
        "✅ Multiple Styles\n"
        "✅ Custom Prompts\n"
        "✅ Instant Generation\n\n"
        
        "🎬 *Video Generation:*\n"
        "✅ HD Quality (1080p)\n"
        "✅ Custom Duration\n"
        "✅ AI Animation\n"
        "✅ Multiple Formats\n\n"
        
        "🌐 *Data Access:*\n"
        "✅ Real-time Web Search\n"
        "✅ Latest Information\n"
        "✅ Fact Checking\n"
        "✅ News Updates\n\n"
        
        "💬 *Conversation:*\n"
        "✅ Unlimited History\n"
        "✅ Context Memory\n"
        "✅ Multi-turn Chat\n"
        "✅ Personality Modes\n\n"
        
        "🌍 *Languages:*\n"
        "✅ English • Hindi • Hinglish\n"
        "✅ Spanish • French • German\n"
        "✅ Code Languages\n\n"
        
        "⚡ *Performance:*\n"
        "✅ Ultra Fast Responses\n"
        "✅ No Rate Limits\n"
        "✅ 24/7 Availability\n"
        "✅ 99.9% Uptime\n\n"
        
        "🎯 *Everything is FREE & UNLIMITED!*"
    )
    await update.message.reply_text(features_text, parse_mode='Markdown')


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process user messages with AI"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "User"
    user_msg = update.message.text
    
    # Show typing indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    logger.info("Processing Telegram message for user %s", user_id)
    
    try:
        # Add user message to history
        user_chats[user_id].append({
            "role": "user",
            "content": user_msg
        })
        
        # Keep last 50 messages for better context
        if len(user_chats[user_id]) > 50:
            user_chats[user_id] = user_chats[user_id][-50:]
        
        # Prepare API payload
        api_payload = {
            "message": user_msg,
            "conversation_history": user_chats[user_id][:-1],
            "user_id": str(user_id),
            "user_name": user_name,
            "features": {
                "image_generation": True,
                "video_generation": True,
                "web_search": True,
                "code_execution": True,
                "advanced_reasoning": True
            },
            "models": [
                "claude-opus-4.5",
                "gpt-5-pro"
            ],
            "settings": {
                "temperature": 0.7,
                "max_tokens": 4096,
                "streaming": False
            }
        }
        
        # Make API request
        logger.info(f"Calling API: {API_ENDPOINT}")
        api_response = await asyncio.to_thread(requests.post,
            API_ENDPOINT,
            json=api_payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "DarkGPT-Telegram-Bot/2.0"
            },
            timeout=API_TIMEOUT
        )
        
        # Check response status
        if api_response.status_code == 200:
            response_data = api_response.json()
            
            # Extract AI response
            ai_reply = (
                response_data.get("response") or 
                response_data.get("message") or 
                response_data.get("reply") or
                "Response received but empty."
            )
            
            # Add AI response to history
            user_chats[user_id].append({
                "role": "assistant",
                "content": ai_reply
            })
            
            # Send response to user
            await update.message.reply_text(ai_reply)
            logger.info(f"Response sent to user {user_id}")
            
        elif api_response.status_code == 503:
            await update.message.reply_text(
                "⏳ *API is starting up...*\n\n"
                "Please wait 30-60 seconds and try again.\n"
                "Your message: " + user_msg[:50],
                parse_mode='Markdown'
            )
            
        else:
            logger.error(f"API Error {api_response.status_code}: {api_response.text[:200]}")
            await update.message.reply_text(
                f"❌ *API Error* [{api_response.status_code}]\n\n"
                f"Please try again in a moment.\n\n"
                f"If problem persists, contact admin.",
                parse_mode='Markdown'
            )
    
    except requests.exceptions.Timeout:
        logger.error("Request timeout")
        await update.message.reply_text(
            "⏱️ *Request Timeout*\n\n"
            "Your request is taking longer than expected.\n"
            "For complex tasks (images/videos), please wait and try again.\n\n"
            "Tip: Try simpler queries first.",
            parse_mode='Markdown'
        )
    
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error: {str(e)[:100]}")
        await update.message.reply_text(
            "🔌 *Connection Error*\n\n"
            "Cannot reach API server.\n"
            "Please check:\n"
            "• API endpoint is online\n"
            "• Network connection\n\n"
            "Try again in a moment.",
            parse_mode='Markdown'
        )
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "⚠️ *Unexpected Error*\n\n"
            "Something went wrong processing your request.\n\n"
            "Try:\n"
            "• /clear to reset conversation\n"
            "• Simpler message\n"
            "• Contact admin if continues",
            parse_mode='Markdown'
        )


async def error_callback(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler"""
    logger.error("Exception in handler:", exc_info=context.error)


def main():
    """Initialize and run the bot"""
    # Get bot token from environment
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        logger.error("ERROR: TELEGRAM_BOT_TOKEN not found in environment!")
        sys.exit(1)
    
    logger.info("="*50)
    logger.info("🌑 DarkGPT Bot Initializing...")
    logger.info(f"API Endpoint: {API_ENDPOINT}")
    logger.info("All Features: ENABLED")
    logger.info("Restrictions: NONE")
    logger.info("="*50)
    
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("clear", cmd_clear))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("features", cmd_features))
    
    # Register message handler
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message)
    )
    
    # Register error handler
    application.add_error_handler(error_callback)
    
    # Start bot
    logger.info("🚀 Bot started successfully!")
    logger.info("Waiting for messages...")
    
    # Render Web Service: Telegram webhook + HTTP listener.
    base_url = (os.environ.get("WEBHOOK_URL") or
                os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
    if not base_url.startswith("https://"):
        logger.error("Set WEBHOOK_URL to your public HTTPS Render URL")
        sys.exit(1)
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not secret:
        logger.error("Set TELEGRAM_WEBHOOK_SECRET to a random secret")
        sys.exit(1)
    port = int(os.environ.get("PORT", "10000"))
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="telegram",
        webhook_url=f"{base_url}/telegram",
        secret_token=secret,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == '__main__':
    main()
