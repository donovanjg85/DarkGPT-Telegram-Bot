
#!/usr/bin/env python3
"""DarkGPT Telegram webhook en Render con memoria en el Bridge."""

import asyncio
import html
import logging
import os
import re
import sys

import requests
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("darkgpt")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
BRIDGE_URL = os.environ.get("BRIDGE_URL", "").rstrip("/")
BRIDGE_SECRET = os.environ.get("BRIDGE_SECRET", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
RENDER_EXTERNAL_URL = os.environ.get(
    "RENDER_EXTERNAL_URL", ""
).rstrip("/")
PORT = int(os.environ.get("PORT", "10000"))

MAX_TEXT = 3000
FENCE = re.compile(r"(?m)^[ ]{0,3}```[^\n]*\n")


def bridge_request(method, path, **kwargs):
    response = requests.request(
        method,
        BRIDGE_URL + path,
        headers={
            "Authorization": "Bearer " + BRIDGE_SECRET
        },
        timeout=(15, 35),
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "🌑 DarkGPT Local\n\n"
        "🤖 Qwen2.5-Coder 3B en MacBook.\n"
        "🧠 Memoria de conversación activada.\n\n"
        "Envíame una pregunta para comenzar.\n\n"
        "Comandos:\n"
        "/start - Iniciar\n"
        "/help - Ayuda\n"
        "/features - Funciones\n"
        "/memoria - Consultar memoria\n"
        "/clear - Borrar historial\n"
        "/olvidar - Borrar historial"
    )


async def help_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "🌑 Ayuda de DarkGPT\n\n"
        "Puedes hacer preguntas, solicitar código "
        "y continuar conversaciones anteriores.\n\n"
        "La memoria se almacena en el Bridge "
        "de tu MacBook.\n\n"
        "No incluye búsqueda web ni generación "
        "de imágenes."
    )


async def features(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "🤖 Funciones de DarkGPT\n\n"
        "✅ Respuestas en español\n"
        "✅ Programación y código\n"
        "✅ Respuestas progresivas\n"
        "✅ Formato de código\n"
        "✅ Memoria persistente\n"
        "✅ Historial separado por chat\n"
        "✅ Eliminación del historial\n\n"
        "La memoria utiliza hasta 12 mensajes "
        "recientes por conversación."
    )


async def memoria(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        result = await asyncio.to_thread(
            bridge_request,
            "GET",
            "/memory",
            params={
                "chat_id": str(update.effective_chat.id)
            },
        )

        count = result.get("messages", 0)
        maximum = result.get("max_messages", 12)

        await update.message.reply_text(
            "🧠 Memoria de DarkGPT\n\n"
            f"Mensajes guardados: {count}\n"
            f"Máximo de contexto: {maximum}\n\n"
            "El historial se almacena en tu MacBook.\n\n"
            "Usa /clear o /olvidar para borrarlo."
        )

    except Exception:
        logger.exception(
            "No se pudo consultar la memoria"
        )
        await update.message.reply_text(
            "❌ No se pudo consultar la memoria.\n"
            "Comprueba que el Bridge esté actualizado."
        )


async def clear(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        result = await asyncio.to_thread(
            bridge_request,
            "POST",
            "/memory/clear",
            json={
                "chat_id": str(update.effective_chat.id)
            },
        )

        deleted = result.get("deleted", 0)

        await update.message.reply_text(
            "🗑️ Memoria eliminada.\n\n"
            f"Mensajes borrados: {deleted}\n\n"
            "Puedes comenzar una conversación nueva."
        )

    except Exception:
        logger.exception(
            "No se pudo borrar la memoria"
        )
        await update.message.reply_text(
            "❌ No se pudo borrar el historial.\n"
            "Comprueba la conexión con el Bridge."
        )


def format_prose(text: str) -> str:
    """Convierte Markdown sencillo a HTML de Telegram."""
    lines = []

    for line in text.splitlines(keepends=True):
        escaped = html.escape(line)

        escaped = re.sub(
            r"^(\s{0,3})#{1,6}\s+(.+?)(\r?\n)?$",
            lambda m: (
                m.group(1)
                + "<b>"
                + m.group(2)
                + "</b>"
                + (m.group(3) or "")
            ),
            escaped,
        )

        escaped = re.sub(
            r"\*\*(.+?)\*\*",
            r"<b>\1</b>",
            escaped,
        )

        escaped = re.sub(
            r"(?<!`)`([^`\n]+)`(?!`)",
            r"<code>\1</code>",
            escaped,
        )

        lines.append(escaped)

    return "".join(lines)


def split_plain(text: str, limit: int = MAX_TEXT):
    """Divide texto sin cortar palabras cuando es posible."""
    while text:
        if len(text) <= limit:
            yield text
            return

        cut = text.rfind("\n", 0, limit + 1)

        if cut <= 0:
            cut = text.rfind(" ", 0, limit + 1)

        if cut <= 0:
            cut = limit
        else:
            cut += 1

        yield text[:cut]
        text = text[cut:]


def extract_ready(buffer: str, final: bool = False):
    """
    Extrae texto y bloques de código completos.

    Mantiene fragmentos incompletos en el buffer
    para evitar cortar palabras entre mensajes.
    """
    sections = []

    while buffer:
        opening = FENCE.search(buffer)

        if not opening:
            if final:
                sections.append(("prose", buffer))
                buffer = ""
            else:
                last_newline = buffer.rfind("\n")

                if last_newline >= 0:
                    safe = last_newline + 1
                    sections.append(
                        ("prose", buffer[:safe])
                    )
                    buffer = buffer[safe:]

            break

        if opening.start():
            sections.append(
                ("prose", buffer[:opening.start()])
            )

        buffer = buffer[opening.start():]
        opening = FENCE.match(buffer)

        closing = re.search(
            r"(?m)^[ ]{0,3}```[ \t]*(?:\n|$)",
            buffer[opening.end():],
        )

        if closing is None:
            if final:
                sections.append(("prose", buffer))
                buffer = ""
            break

        code_start = opening.end()
        code_end = code_start + closing.start()
        end = code_start + closing.end()

        sections.append(
            ("code", buffer[code_start:code_end])
        )

        closing_text = buffer[code_end:end]

        buffer = (
            ("\n" if closing_text.endswith("\n") else "")
            + buffer[end:]
        )

    return sections, buffer


async def mantener_escribiendo(bot, chat_id: int):
    """Mantiene el indicador de escritura de Telegram."""
    try:
        while True:
            try:
                await bot.send_chat_action(
                    chat_id=chat_id,
                    action=ChatAction.TYPING,
                )
            except Exception:
                logger.exception(
                    "Error en indicador de escritura"
                )

            await asyncio.sleep(4)

    except asyncio.CancelledError:
        return


async def deliver_job(message, status, prompt, chat_id):
    """Envía la pregunta al Bridge con ID de conversación."""

    created = await asyncio.to_thread(
        bridge_request,
        "POST",
        "/jobs",
        json={
            "message": prompt,
            "chat_id": str(chat_id),
        },
    )

    job_id = created["job_id"]

    received = 0
    pending = ""
    failures = 0
    started = asyncio.get_running_loop().time()
    last_delivery = started
    delivered = 0

    async def send_section(kind, text):
        nonlocal delivered, last_delivery

        if not text.strip():
            return

        for piece in split_plain(text):
            if not piece.strip():
                continue

            if kind == "code":
                formatted = (
                    "<pre><code>"
                    + html.escape(piece)
                    + "</code></pre>"
                )
            else:
                formatted = format_prose(piece)

            try:
                await message.reply_text(
                    formatted,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )

            except Exception:
                logger.exception(
                    "Error enviando HTML; usando texto plano"
                )

                await message.reply_text(
                    piece,
                    parse_mode=None,
                    disable_web_page_preview=True,
                )

            delivered += 1
            last_delivery = (
                asyncio.get_running_loop().time()
            )

    async def drain(force=False):
        nonlocal pending

        elapsed = (
            asyncio.get_running_loop().time()
            - last_delivery
        )

        if (
            not force
            and len(pending) < 750
            and (not pending or elapsed < 12)
        ):
            return

        sections, pending = extract_ready(
            pending,
            final=force,
        )

        for kind, text in sections:
            await send_section(kind, text)

    while True:
        elapsed = (
            asyncio.get_running_loop().time()
            - started
        )

        if elapsed > 1200:
            await drain(force=True)

            await status.edit_text(
                "⏱️ Se alcanzó el tiempo máximo "
                "de seguimiento de 20 minutos."
            )
            return

        await asyncio.sleep(2)

        try:
            job = await asyncio.to_thread(
                bridge_request,
                "GET",
                "/jobs/" + job_id,
            )
            failures = 0

        except requests.exceptions.RequestException:
            failures += 1

            if failures > 10:
                await drain(force=True)
                raise

            await asyncio.sleep(
                min(failures * 2, 15)
            )
            continue

        chunks = job.get("chunks") or []

        if (
            not isinstance(chunks, list)
            or len(chunks) < received
        ):
            raise ValueError(
                "Fragmentos inválidos del Bridge"
            )

        for chunk in chunks[received:]:
            if not isinstance(chunk, str):
                raise ValueError(
                    "Fragmento no válido"
                )

            pending += chunk

        received = len(chunks)
        state = job.get("state")

        finished = state in (
            "done",
            "limit",
            "error",
        )

        await drain(force=finished)

        if state == "running":
            continue

        if state == "done":
            await status.edit_text(
                "✅ Respuesta terminada.\n"
                f"Mensajes enviados: {delivered}."
            )
            return

        if state == "limit":
            await status.edit_text(
                "⚠️ Respuesta incompleta: "
                "Qwen alcanzó el límite de tokens."
            )
            return

        if state == "error":
            error = str(
                job.get("error") or "Revisa Bridge"
            )[:180]

            await status.edit_text(
                "❌ Generación interrumpida: "
                + error
            )
            return

        raise ValueError(
            "Estado desconocido: " + str(state)
        )


async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message or not message.text:
        return

    if len(message.text) > 4000:
        await message.reply_text(
            "El mensaje supera los 4000 caracteres."
        )
        return

    status = await message.reply_text(
        "⏳ DarkGPT está procesando tu solicitud…\n"
        "🤖 Qwen2.5 está generando la respuesta."
    )

    typing_task = asyncio.create_task(
        mantener_escribiendo(
            context.bot,
            update.effective_chat.id,
        )
    )

    try:
        await deliver_job(
            message,
            status,
            message.text,
            update.effective_chat.id,
        )

    except requests.exceptions.Timeout:
        logger.exception(
            "Tiempo de espera agotado"
        )

        await status.edit_text(
            "⏱️ La IA tardó demasiado.\n"
            "Prueba una pregunta más corta."
        )

    except requests.exceptions.HTTPError as exc:
        code = (
            exc.response.status_code
            if exc.response is not None
            else "?"
        )

        logger.error(
            "Bridge devolvió HTTP %s", code
        )

        await status.edit_text(
            "❌ El servidor de IA devolvió un error.\n"
            "Revisa Bridge y llama-server."
        )

    except (
        requests.exceptions.RequestException,
        ValueError,
    ):
        logger.exception(
            "Fallo al consultar Bridge"
        )

        await status.edit_text(
            "🔌 No se pudo consultar la IA local.\n"
            "Comprueba la MacBook y el túnel SSH."
        )

    except Exception:
        logger.exception(
            "Error inesperado procesando mensaje"
        )

        try:
            await status.edit_text(
                "❌ Ocurrió un error procesando "
                "la solicitud.\n"
                "Revisa los logs de Render."
            )
        except Exception:
            logger.exception(
                "No se pudo actualizar el estado"
            )

    finally:
        typing_task.cancel()
        await typing_task


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.error(
        "Error procesando actualización de Telegram: %s",
        context.error,
        exc_info=context.error,
    )


async def main():
    if (
        not TOKEN
        or not BRIDGE_SECRET
        or not BRIDGE_URL.startswith("https://")
    ):
        raise SystemExit(
            "Faltan TELEGRAM_BOT_TOKEN, BRIDGE_SECRET "
            "o BRIDGE_URL (HTTPS)."
        )

    if (
        not WEBHOOK_SECRET
        or not RENDER_EXTERNAL_URL.startswith("https://")
    ):
        raise SystemExit(
            "Faltan WEBHOOK_SECRET o "
            "RENDER_EXTERNAL_URL (HTTPS)."
        )

    app = (
        Application.builder()
        .token(TOKEN)
        .updater(None)
        .concurrent_updates(True)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )
    app.add_handler(
        CommandHandler("help", help_cmd)
    )
    app.add_handler(
        CommandHandler("features", features)
    )
    app.add_handler(
        CommandHandler("memoria", memoria)
    )
    app.add_handler(
        CommandHandler("clear", clear)
    )
    app.add_handler(
        CommandHandler("olvidar", clear)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            message_handler,
        )
    )

    app.add_error_handler(error_handler)

    from aiohttp import web

    async def health(request):
        return web.json_response(
            {"status": "ok"}
        )

    async def webhook(request):
        secret = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token",
            "",
        )

        if secret != WEBHOOK_SECRET:
            return web.Response(status=403)

        try:
            data = await request.json()
            update = Update.de_json(
                data,
                app.bot,
            )

            if update is None:
                return web.Response(status=400)

            await app.update_queue.put(update)

        except (ValueError, TypeError):
            logger.exception(
                "Actualización inválida"
            )
            return web.Response(status=400)

        return web.Response(text="OK")

    server = web.Application(
        client_max_size=1024 * 1024
    )

    server.router.add_get("/", health)
    server.router.add_get("/health", health)
    server.router.add_post(
        "/telegram",
        webhook,
    )

    runner = web.AppRunner(server)

    await app.initialize()
    await app.start()

    try:
        await runner.setup()

        site = web.TCPSite(
            runner,
            "0.0.0.0",
            PORT,
        )

        await site.start()

        await app.bot.set_webhook(
            url=RENDER_EXTERNAL_URL + "/telegram",
            secret_token=WEBHOOK_SECRET,
            allowed_updates=["message"],
            drop_pending_updates=False,
        )

        logger.info(
            "Webhook configurado en %s/telegram",
            RENDER_EXTERNAL_URL,
        )

        await asyncio.Event().wait()

    finally:
        await runner.cleanup()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
