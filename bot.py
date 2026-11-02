#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DarkGPT Telegram Bot para Bridge con trabajos asincrónicos."""
import asyncio
import logging
import os
import sys
import time
import requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
BRIDGE_URL = os.getenv('BRIDGE_URL', '').rstrip('/')
BRIDGE_SECRET = os.getenv('BRIDGE_SECRET', '')
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
HEADERS = {'Authorization': 'Bearer ' + BRIDGE_SECRET}
MAX_WAIT = 1200

def submit_job(message):
    r = requests.post(BRIDGE_URL + '/jobs', json={'message': message}, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.json()['id']

def fetch_job(job_id):
    r = requests.get(BRIDGE_URL + '/jobs/' + job_id, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.json()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('🌑 DarkGPT Local\n🤖 Qwen2.5-Coder 3B en MacBook.\nEnvíame una pregunta. Para respuestas largas esperaré a que termine la IA.')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Escribe tu pregunta. /start /help /features /clear. Cada consulta es independiente.')

async def features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Respuestas en español, programación y textos largos divididos en mensajes.')

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('✅ Este bot no guarda historial de conversación.')

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    if len(prompt) > 4000:
        return await update.message.reply_text('El mensaje supera los 4000 caracteres.')
    notice = await update.message.reply_text('⏳ Qwen2.5 está procesando tu solicitud...')
    try:
        job_id = await asyncio.to_thread(submit_job, prompt)
        started = time.monotonic()
        while time.monotonic() - started < MAX_WAIT:
            await asyncio.sleep(8)
            job = await asyncio.to_thread(fetch_job, job_id)
            if job.get('status') == 'done':
                answer = job.get('response', '')
                if not answer:
                    raise ValueError('Respuesta vacía')
                await notice.edit_text('✅ Respuesta terminada:')
                for i in range(0, len(answer), 3500):
                    await update.message.reply_text(answer[i:i+3500])
                return
            if job.get('status') == 'error':
                logger.error('Bridge job failed: %s', job.get('error'))
                return await notice.edit_text('❌ Qwen2.5 no pudo completar la respuesta. Revisa los registros del Bridge.')
        await notice.edit_text('⏱️ La respuesta tardó demasiado. Prueba una solicitud más corta.')
    except (requests.RequestException, KeyError, ValueError):
        logger.exception('Fallo comunicando con Bridge')
        await notice.edit_text('🔌 Error de conexión con el Bridge. Comprueba Mac, Cloudflare y BRIDGE_URL.')

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/', '/health'):
            return self.send_error(404)
        payload = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, fmt, *args):
        pass

def main():
    if not (BRIDGE_URL.startswith('https://') and BRIDGE_SECRET and TOKEN):
        raise SystemExit('Configura BRIDGE_URL, BRIDGE_SECRET y TELEGRAM_BOT_TOKEN en Render')
    server = ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '10000'))), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(CommandHandler('features', features))
    app.add_handler(CommandHandler('clear', clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    logger.info('DarkGPT iniciado')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
