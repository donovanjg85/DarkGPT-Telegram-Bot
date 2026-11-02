#!/usr/bin/env python3
"""DarkGPT Telegram webhook on Render, backed by an authenticated local bridge."""
import asyncio
import logging
import os
import sys

import requests
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('darkgpt')

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
BRIDGE_URL = os.environ.get('BRIDGE_URL', '').rstrip('/')
BRIDGE_SECRET = os.environ.get('BRIDGE_SECRET', '')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', '')
RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL', '').rstrip('/')
PORT = int(os.environ.get('PORT', '10000'))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('🌑 DarkGPT Local\n\n🤖 Qwen2.5-Coder 3B en MacBook.\nEnvía una pregunta para recibir una respuesta.\n\nComandos: /start /help /features /clear\n\nLa MacBook, llama-server, Bridge y Cloudflare deben permanecer activos.')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Envía texto para consultar la IA local. No incluye búsqueda web ni generación de imágenes.')

async def features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Respuestas en español, programación y consultas de texto. Cada pregunta se procesa independientemente.')

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('✅ Este bot no conserva historial de conversación.')

def bridge_request(method, path, **kwargs):
    response = requests.request(
        method, BRIDGE_URL + path,
        headers={'Authorization': 'Bearer ' + BRIDGE_SECRET},
        timeout=(15, 35), **kwargs
    )
    response.raise_for_status()
    return response.json()


async def deliver_job(message, status, prompt):
    created = await asyncio.to_thread(bridge_request, 'POST', '/jobs', json={'message': prompt})
    job_id = created['job_id']
    sent = 0
    previous_state = None
    # Bridge retains all chunks so a transient network error can be retried safely.
    started = asyncio.get_running_loop().time()
    failures = 0
    while True:
        if asyncio.get_running_loop().time() - started > 1200:
            await status.edit_text('⏱️ Se alcanzó el tiempo máximo de seguimiento (20 min).')
            return
        await asyncio.sleep(3)
        try:
            job = await asyncio.to_thread(bridge_request, 'GET', '/jobs/' + job_id)
            failures = 0
        except requests.exceptions.RequestException:
            failures += 1
            if failures > 10:
                raise
            await asyncio.sleep(min(failures * 2, 15))
            continue
        chunks = job.get('chunks') or []
        # Each chunk is <= 1600 characters; Telegram plain text allows 4096.
        for chunk in chunks[sent:]:
            if chunk:
                await message.reply_text(chunk)
            sent += 1
        state = job.get('state')
        if sent and state == 'running' and (sent != previous_state):
            await status.edit_text(f'⏳ DarkGPT sigue generando… Partes recibidas: {sent}')
        previous_state = sent
        if state == 'done':
            await status.edit_text('✅ Respuesta terminada.')
            return
        if state == 'limit':
            await status.edit_text('⚠️ Respuesta incompleta: Qwen alcanzó el límite de tokens. Puedes pedir una continuación.')
            return
        if state == 'error':
            await status.edit_text('❌ Se interrumpió la generación. ' + str(job.get('error') or 'Revisa el Bridge.')[:180])
            return
        if state != 'running':
            raise ValueError('Estado desconocido del Bridge: ' + str(state))


async def mantener_escribiendo(bot, chat_id: int):
    """Renueva el indicador de escritura hasta que termine la respuesta."""
    try:
        while True:
            try:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                logger.exception('No se pudo actualizar el indicador de escritura')
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        return

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return
    if len(message.text) > 4000:
        await message.reply_text('El mensaje supera los 4000 caracteres.')
        return

    # Visible, persistent progress message; Telegram's typing indicator alone expires.
    status = await message.reply_text('⏳ DarkGPT está procesando tu solicitud…\n🤖 Qwen2.5 está generando la respuesta.')
    typing_task = asyncio.create_task(mantener_escribiendo(context.bot, update.effective_chat.id))
    try:
        await deliver_job(message, status, message.text)
    except requests.exceptions.Timeout:
        logger.exception('Tiempo de espera agotado consultando Bridge')
        await status.edit_text('⏱️ La IA tardó demasiado. Prueba una pregunta más corta.')
    except requests.exceptions.HTTPError as exc:
        logger.error('Bridge devolvió HTTP %s', exc.response.status_code if exc.response is not None else '?')
        await status.edit_text('❌ El servidor de IA devolvió un error. Revisa Bridge y llama-server.')
    except (requests.exceptions.RequestException, ValueError):
        logger.exception('Fallo al consultar Bridge')
        await status.edit_text('🔌 No se pudo consultar la IA local. Comprueba la MacBook y Cloudflare.')
    except Exception:
        logger.exception('Error inesperado procesando mensaje')
        try:
            await status.edit_text('❌ Ocurrió un error procesando la solicitud. Revisa los logs de Render.')
        except Exception:
            logger.exception('No se pudo actualizar el estado')
    finally:
        typing_task.cancel()
        await typing_task

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error('Error procesando actualización de Telegram: %s', context.error, exc_info=context.error)

async def main():
    if not TOKEN or not BRIDGE_SECRET or not BRIDGE_URL.startswith('https://'):
        raise SystemExit('Faltan TELEGRAM_BOT_TOKEN, BRIDGE_SECRET o BRIDGE_URL (HTTPS).')
    if not WEBHOOK_SECRET or not RENDER_EXTERNAL_URL.startswith('https://'):
        raise SystemExit('Faltan WEBHOOK_SECRET o RENDER_EXTERNAL_URL (HTTPS).')
    app = Application.builder().token(TOKEN).updater(None).concurrent_updates(True).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(CommandHandler('features', features))
    app.add_handler(CommandHandler('clear', clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)

    # Aiohttp responds to Telegram immediately, then processes the update asynchronously.
    from aiohttp import web

    async def health(request):
        return web.json_response({'status': 'ok'})

    async def webhook(request):
        if request.headers.get('X-Telegram-Bot-Api-Secret-Token', '') != WEBHOOK_SECRET:
            return web.Response(status=403)
        try:
            data = await request.json()
            update = Update.de_json(data, app.bot)
            if update is None:
                return web.Response(status=400)
            await app.update_queue.put(update)
        except (ValueError, TypeError):
            logger.exception('Actualización inválida')
            return web.Response(status=400)
        return web.Response(text='OK')

    server = web.Application(client_max_size=1024 * 1024)
    server.router.add_get('/', health)
    server.router.add_get('/health', health)
    server.router.add_post('/telegram', webhook)
    runner = web.AppRunner(server)
    await app.initialize()
    await app.start()
    try:
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        await app.bot.set_webhook(
            url=RENDER_EXTERNAL_URL + '/telegram',
            secret_token=WEBHOOK_SECRET,
            allowed_updates=['message'],
            drop_pending_updates=False,
        )
        logger.info('Webhook configurado en %s/telegram', RENDER_EXTERNAL_URL)
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await app.stop()
        await app.shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
