#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DarkGPT Telegram Bot conectado a un modelo local mediante Bridge autenticado."""
import asyncio
import logging
import os
import sys
import requests
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
BRIDGE_URL = os.getenv('BRIDGE_URL', '').rstrip('/')
BRIDGE_SECRET = os.getenv('BRIDGE_SECRET', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TIMEOUT = 190

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🌑 DarkGPT Local\n\n🤖 Modelo: Qwen2.5-Coder 3B en MacBook.\n'
        'Envía una pregunta para recibir una respuesta.\n\n'
        'Comandos: /start /help /features /clear\n\n'
        'La MacBook y su túnel deben permanecer encendidos.')

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Escribe una pregunta en texto. El bot la enviará a tu IA local.\n'
        'No incluye generación de imágenes, videos ni búsqueda web en tiempo real.')

async def cmd_features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Funciones actuales: respuestas en español, ayuda con programación y '
        'consultas de texto. Cada pregunta se procesa de forma independiente.')

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('✅ Listo. Este bot no almacena historial de conversación.')

def request_bridge(message):
    response = requests.post(
        BRIDGE_URL + '/chat',
        json={'message': message},
        headers={'Authorization': 'Bearer ' + BRIDGE_SECRET},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    result = response.json()
    answer = result.get('response')
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError('Respuesta vacía o inválida del Bridge')
    return answer

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    if len(message) > 4000:
        await update.message.reply_text('El mensaje supera el límite de 4000 caracteres.')
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id,
                                       action=ChatAction.TYPING)
    try:
        # requests es síncrono: usar hilo para no bloquear otras conversaciones.
        answer = await asyncio.to_thread(request_bridge, message)
        for i in range(0, len(answer), 3900):
            await update.message.reply_text(answer[i:i+3900])
    except requests.exceptions.Timeout:
        await update.message.reply_text('⏱️ La IA tardó demasiado en responder. Intenta una pregunta más corta.')
    except requests.exceptions.HTTPError as exc:
        logger.error('Bridge HTTP error: %s', exc.response.status_code if exc.response else 'unknown')
        await update.message.reply_text('❌ El servidor de IA devolvió un error. Revisa Bridge y Cloudflare.')
    except (requests.exceptions.RequestException, ValueError):
        logger.exception('Error consultando el Bridge')
        await update.message.reply_text('🔌 No se pudo consultar la IA local. Comprueba la Mac y el túnel.')

def main():
    if not all((BRIDGE_URL.startswith('https://'), BRIDGE_SECRET, TELEGRAM_BOT_TOKEN)):
        raise SystemExit('Configura BRIDGE_URL (HTTPS), BRIDGE_SECRET y TELEGRAM_BOT_TOKEN en Render.')
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('help', cmd_help))
    app.add_handler(CommandHandler('features', cmd_features))
    app.add_handler(CommandHandler('clear', cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
    logger.info('DarkGPT Local iniciado')
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
