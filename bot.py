
#!/usr/bin/env python3
"""DarkGPT Telegram Bot - Render + Bridge local + Qwen."""

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


# ============================================================
# CONFIGURACION
# ============================================================

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

# Limite conservador por mensaje.
MAX_TEXT = 3000

# Detecta apertura de bloques Markdown.
FENCE = re.compile(
    r"(?m)^[ ]{0,3}```[^\n]*\n"
)

# Detecta cierre de bloques Markdown.
CLOSING_FENCE = re.compile(
    r"(?m)^[ ]{0,3}```[ \t]*(?:\r?\n|$)"
)


# ============================================================
# COMANDOS TELEGRAM
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "🌑 DarkGPT Local\n\n"
        "🤖 Qwen2.5-Coder 3B en MacBook.\n\n"
        "Envía una pregunta para recibir una respuesta.\n\n"
        "Comandos:\n"
        "/start\n"
        "/help\n"
        "/features\n"
        "/clear\n\n"
        "La MacBook, llama-server, Bridge y Cloudflare "
        "deben permanecer activos."
    )


async def help_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "Envía texto para consultar la IA local.\n\n"
        "El bot admite respuestas largas y código Python.\n"
        "No incluye búsqueda web ni generación de imágenes."
    )


async def features(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "🤖 DarkGPT\n\n"
        "• Respuestas en español.\n"
        "• Programación y consultas de texto.\n"
        "• Respuestas progresivas en varios mensajes.\n"
        "• Bloques de código formateados.\n"
        "• Cada pregunta se procesa independientemente."
    )


async def clear(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "✅ Este bot no conserva historial de conversación."
    )


# ============================================================
# CONEXION CON BRIDGE
# ============================================================

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


# ============================================================
# FORMATO DE MENSAJES
# ============================================================

def format_prose(text: str) -> str:
    """
    Convierte Markdown sencillo a HTML compatible
    con Telegram.

    No modifica bloques de codigo.
    """

    lines = []

    for line in text.splitlines(keepends=True):

        escaped = html.escape(line)

        # Encabezados Markdown.
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

        # Negritas.
        escaped = re.sub(
            r"\*\*(.+?)\*\*",
            r"<b>\1</b>",
            escaped,
        )

        # Codigo en linea.
        escaped = re.sub(
            r"(?<!`)`([^`\n]+)`(?!`)",
            r"<code>\1</code>",
            escaped,
        )

        lines.append(escaped)

    return "".join(lines)


def split_plain(text: str, limit: int = MAX_TEXT):
    """
    Divide textos largos priorizando saltos de linea
    y espacios.

    No elimina caracteres del texto original.
    """

    while text:

        if len(text) <= limit:
            yield text
            return

        # Preferir salto de linea.
        cut = text.rfind("\n", 0, limit + 1)

        # Si no existe, buscar espacio.
        if cut <= 0:
            cut = text.rfind(" ", 0, limit + 1)

        # Ultimo recurso: corte por longitud.
        if cut <= 0:
            cut = limit
        else:
            cut += 1

        yield text[:cut]
        text = text[cut:]


# ============================================================
# CORRECCION PRINCIPAL: NO CORTAR PALABRAS
# ============================================================

def extract_ready(buffer: str, final: bool = False):
    """
    Extrae solamente contenido listo para Telegram.

    Reglas:
    - No enviar una linea incompleta.
    - No dividir bloques Markdown sin cerrar.
    - Conservar los saltos de linea.
    - Entregar el resto al finalizar la generacion.

    Devuelve:
        (sections, remaining)

    Cada seccion es:
        ("prose", texto)
        ("code", texto)
    """

    sections = []

    while buffer:

        opening = FENCE.search(buffer)

        # ----------------------------------------------------
        # NO HAY APERTURA COMPLETA DE BLOQUE DE CODIGO
        # ----------------------------------------------------

        if opening is None:

            if final:
                # La generacion ya termino.
                if buffer.strip():
                    sections.append(("prose", buffer))

                buffer = ""

            else:
                # Solo liberar lineas completas.
                # La ultima linea queda pendiente.
                last_newline = buffer.rfind("\n")

                if last_newline >= 0:

                    ready = buffer[:last_newline + 1]
                    buffer = buffer[last_newline + 1:]

                    if ready.strip():
                        sections.append(("prose", ready))

            break

        # ----------------------------------------------------
        # TEXTO ANTES DEL BLOQUE DE CODIGO
        # ----------------------------------------------------

        if opening.start() > 0:

            prose = buffer[:opening.start()]

            if prose.strip():
                sections.append(("prose", prose))

            buffer = buffer[opening.start():]

        opening = FENCE.match(buffer)

        if opening is None:
            break

        # ----------------------------------------------------
        # BUSCAR EL CIERRE DEL BLOQUE DE CODIGO
        # ----------------------------------------------------

        content_start = opening.end()

        closing = CLOSING_FENCE.search(
            buffer[content_start:]
        )

        if closing is None:

            if final:
                # El modelo termino sin cerrar el bloque.
                # Conservar todo el contenido.
                if buffer.strip():
                    sections.append(("prose", buffer))

                buffer = ""

            # Todavia genera: esperar el cierre.
            break

        code_end = content_start + closing.start()
        block_end = content_start + closing.end()

        code_text = buffer[content_start:code_end]

        if code_text.strip():
            sections.append(("code", code_text))

        closing_text = buffer[code_end:block_end]
        remaining = buffer[block_end:]

        # Conservar el salto despues del bloque.
        if closing_text.endswith("\n"):
            buffer = "\n" + remaining
        else:
            buffer = remaining

    return sections, buffer


# ============================================================
# GENERACION Y ENTREGA PROGRESIVA
# ============================================================

async def deliver_job(message, status, prompt):

    # Crear trabajo en Bridge.
    created = await asyncio.to_thread(
        bridge_request,
        "POST",
        "/jobs",
        json={"message": prompt},
    )

    job_id = created["job_id"]

    received = 0
    pending = ""
    failures = 0
    delivered = 0

    loop = asyncio.get_running_loop()

    started = loop.time()
    last_delivery = started

    # --------------------------------------------------------
    # ENVIAR UNA SECCION
    # --------------------------------------------------------

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
                    "Error enviando HTML. "
                    "Reintentando como texto plano."
                )

                await message.reply_text(
                    piece,
                    parse_mode=None,
                    disable_web_page_preview=True,
                )

            delivered += 1
            last_delivery = loop.time()

    # --------------------------------------------------------
    # EXTRAER CONTENIDO LISTO
    # --------------------------------------------------------

    async def drain(force=False):

        nonlocal pending

        if not force:

            elapsed = loop.time() - last_delivery

            # Evitar demasiados mensajes pequeños.
            if len(pending) < 750 and elapsed < 12:
                return

        sections, pending = extract_ready(
            pending,
            final=force,
        )

        for kind, text in sections:
            await send_section(kind, text)

    # --------------------------------------------------------
    # CONSULTAR BRIDGE PERIODICAMENTE
    # --------------------------------------------------------

    while True:

        if loop.time() - started > 1200:

            await drain(force=True)

            await status.edit_text(
                "⏱️ Se alcanzó el tiempo máximo de "
                "seguimiento (20 minutos).\n"
                "La respuesta puede estar incompleta."
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

        if not isinstance(chunks, list):
            raise ValueError(
                "Fragmentos invalidos del Bridge"
            )

        if len(chunks) < received:
            raise ValueError(
                "El Bridge redujo los fragmentos recibidos"
            )

        # Agregar solo fragmentos nuevos.
        for chunk in chunks[received:]:

            if not isinstance(chunk, str):
                raise ValueError(
                    "Fragmento no valido del Bridge"
                )

            pending += chunk

        received = len(chunks)

        state = job.get("state")

        # Forzar envio cuando Qwen termina.
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
                "⚠️ Respuesta incompleta.\n"
                "Qwen alcanzó el límite de tokens.\n"
                f"Mensajes enviados: {delivered}."
            )

            return

        if state == "error":

            error = str(
                job.get("error") or "Revisa Bridge"
            )[:180]

            await status.edit_text(
                "❌ Generación interrumpida:\n"
                + error
            )

            return

        raise ValueError(
            "Estado desconocido del Bridge: "
            + str(state)
        )


# ============================================================
# INDICADOR DE ESCRITURA
# ============================================================

async def mantener_escribiendo(bot, chat_id: int):

    try:

        while True:

            try:

                await bot.send_chat_action(
                    chat_id=chat_id,
                    action=ChatAction.TYPING,
                )

            except Exception:

                logger.exception(
                    "No se pudo actualizar el indicador"
                )

            await asyncio.sleep(4)

    except asyncio.CancelledError:
        return


# ============================================================
# RECIBIR MENSAJES DEL USUARIO
# ============================================================

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

        logger.error(
            "Bridge devolvió HTTP %s",
            (
                exc.response.status_code
                if exc.response is not None
                else "?"
            ),
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
            "Comprueba la MacBook y Cloudflare."
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


# ============================================================
# MANEJADOR GLOBAL DE ERRORES
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.error(
        "Error procesando actualización de Telegram: %s",
        context.error,
        exc_info=context.error,
    )


# ============================================================
# SERVIDOR WEBHOOK PARA RENDER
# ============================================================

async def main():

    if (
        not TOKEN
        or not BRIDGE_SECRET
        or not BRIDGE_URL.startswith("https://")
    ):

        raise SystemExit(
            "Faltan TELEGRAM_BOT_TOKEN, "
            "BRIDGE_SECRET o BRIDGE_URL (HTTPS)."
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
        CommandHandler("clear", clear)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            message_handler,
        )
    )

    app.add_error_handler(error_handler)

    from aiohttp import web

    # --------------------------------------------------------
    # HEALTH CHECK
    # --------------------------------------------------------

    async def health(request):

        return web.json_response(
            {"status": "ok"}
        )

    # --------------------------------------------------------
    # WEBHOOK DE TELEGRAM
    # --------------------------------------------------------

    async def webhook(request):

        received_secret = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token",
            "",
        )

        if received_secret != WEBHOOK_SECRET:
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

    # --------------------------------------------------------
    # INICIAR SERVIDOR
    # --------------------------------------------------------

    server = web.Application(
        client_max_size=1024 * 1024
    )

    server.router.add_get(
        "/",
        health,
    )

    server.router.add_get(
        "/health",
        health,
    )

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


# ============================================================
# EJECUCION
# ============================================================

if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        pass
