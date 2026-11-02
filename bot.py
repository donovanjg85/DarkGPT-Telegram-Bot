#!/usr/bin/env python3
"""DarkGPT Telegram webhook on Render, backed by an authenticated local bridge."""
import asyncio
import html
import re
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


def render_telegram_html(text: str) -> str:
    """Format common Markdown as safe Telegram HTML, including fenced code."""
    parts = []
    in_code = False
    code_lines = []
    for line in text.splitlines(keepends=True):
        match = re.match(r"^\s*```([a-zA-Z0-9_+.-]*)\s*$", line.rstrip("\r\n"))
        if match:
            if in_code:
                parts.append('<pre><code>' + html.escape(''.join(code_lines)) + '</code></pre>\n')
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        clean = html.escape(line)
        # Headings are bold, not literal ### markers.
        clean = re.sub(r'^\s{0,3}#{1,6}\s+(.+?)(\n?)$', r'<b>\1</b>\2', clean)
        clean = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', clean)
        clean = re.sub(r'(?<!\*)`([^`\n]+)`(?!`)', r'<code>\1</code>', clean)
        parts.append(clean)
    if in_code:
        parts.append('<pre><code>' + html.escape(''.join(code_lines)) + '</code></pre>')
    return ''.join(parts).strip() or html.escape(text)


def take_safe_piece(text: str, limit: int = 2600):
    """Split at a newline when possible; keep enough room for HTML markup."""
    if len(text) <= limit:
        return text, ''
    cut = text.rfind('\n', 0, limit)
    if cut < limit // 3:
        cut = text.rfind(' ', 0, limit)
    if cut < limit // 3:
        cut = limit
    else:
        cut += 1
    return text[:cut], text[cut:]


async def deliver_job(message, status, prompt):
    created = await asyncio.to_thread(bridge_request, 'POST', '/jobs', json={'message': prompt})
    job_id = created['job_id']
    received = 0
    pending = ''
    failures = 0
    started = asyncio.get_running_loop().time()
    last_delivery = started
    delivered = 0

    async def send_piece(piece):
        nonlocal delivered, last_delivery
        if not piece.strip():
            return
        formatted = render_telegram_html(piece)
        try:
            await message.reply_text(formatted, parse_mode='HTML', disable_web_page_preview=True)
        except Exception:
            logger.exception('HTML no admitido; enviando texto plano')
            await message.reply_text(piece, parse_mode=None, disable_web_page_preview=True)
        delivered += 1
        last_delivery = asyncio.get_running_loop().time()

    async def drain(force=False):
        nonlocal pending
        # Send the first part promptly; subsequent messages at moderate intervals.
        if not force and len(pending) < 750 and (not pending or asyncio.get_running_loop().time() - last_delivery < 12):
            return
        while len(pending) > 2600:
            piece, pending = take_safe_piece(pending)
            await send_piece(piece)
        if force or len(pending) >= 750 or (pending and asyncio.get_running_loop().time() - last_delivery >= 12):
            piece, pending = pending, ''
            await send_piece(piece)

    while True:
        if asyncio.get_running_loop().time() - started > 1200:
            await drain(force=True)
            await status.edit_text('⏱️ Se alcanzó el tiempo máximo de seguimiento (20 min). Respuesta posiblemente incompleta.')
            return
        await asyncio.sleep(2)
        try:
            job = await asyncio.to_thread(bridge_request, 'GET', '/jobs/' + job_id)
            failures = 0
        except requests.exceptions.RequestException:
            failures += 1
            if failures > 10:
                await drain(force=True)
                raise
            await asyncio.sleep(min(failures * 2, 15))
            continue
        chunks = job.get('chunks') or []
        if not isinstance(chunks, list) or len(chunks) < received:
            raise ValueError('Fragmentos inválidos del Bridge')
        for chunk in chunks[received:]:
            if not isinstance(chunk, str):
                raise ValueError('Fragmento no válido')
            pending += chunk
        received = len(chunks)
        state = job.get('state')
        await drain(force=state in ('done', 'limit', 'error'))
        if state == 'running':
            continue
        if state == 'done':
            await status.edit_text(f'✅ Respuesta terminada. Mensajes enviados: {delivered}.')
            return
        if state == 'limit':
            await status.edit_text('⚠️ Respuesta incompleta: Qwen alcanzó el límite de tokens.')
            return
        if state == 'error':
            await status.edit_text('❌ Generación interrumpida: ' + str(job.get('error') or 'Revisa Bridge')[:180])
            return
        raise ValueError('Estado desconocido: ' + str(state))

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
