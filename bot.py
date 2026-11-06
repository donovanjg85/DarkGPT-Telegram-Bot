
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DarkGPT Telegram Bot
Compatible con:
- Render
- Qwen2.5-Coder 3B
- llama.cpp
- Bridge con memoria SQLite
- Telegram Webhook
"""
import hmac
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


# ==========================================
# CONFIGURACION GENERAL
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger("darkgpt")

TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN", ""
).strip()

BRIDGE_URL = os.environ.get(
    "BRIDGE_URL", ""
).rstrip("/")

BRIDGE_SECRET = os.environ.get(
    "BRIDGE_SECRET", ""
)

WEBHOOK_SECRET = os.environ.get(
    "WEBHOOK_SECRET", ""
)

RENDER_EXTERNAL_URL = os.environ.get(
    "RENDER_EXTERNAL_URL", ""
).rstrip("/")

PORT = int(
    os.environ.get("PORT", "10000")
)

MAX_TEXT = 3000

FENCE = re.compile(
    r"(?m)^[ ]{0,3}```[^\n]*\n"
)


# ==========================================
# CONEXION CON EL BRIDGE
# ==========================================

def bridge_request(method, path, **kwargs):
    """
    Consulta el Bridge instalado en la MacBook.
    Utiliza autenticacion Bearer.
    """

    response = requests.request(
        method,
        BRIDGE_URL + path,
        headers={
            "Authorization": "Bearer " + BRIDGE_SECRET
        },
        timeout=(15, 35),
        **kwargs
    )

    response.raise_for_status()

    return response.json()


# ==========================================
# COMANDO /start
# ==========================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "🌑 DarkGPT Local\n\n"
        "🤖 Qwen2.5-Coder 3B en MacBook.\n"
        "🧠 Memoria de conversación activada.\n\n"
        "Envíame una pregunta para comenzar.\n\n"
        "Comandos disponibles:\n"
        "/start - Iniciar\n"
        "/help - Ayuda\n"
        "/features - Funciones\n"
        "/memoria - Consultar memoria\n"
        "/clear - Borrar historial\n"
        "/olvidar - Borrar historial"
    )


# ==========================================
# COMANDO /help
# ==========================================

async def help_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "🌑 Ayuda de DarkGPT\n\n"
        "Puedes hacer preguntas, solicitar código "
        "y continuar conversaciones anteriores.\n\n"
        "La memoria se almacena en el Bridge "
        "de tu MacBook.\n\n"
        "No incluye búsqueda web ni "
        "generación de imágenes."
    )


# ==========================================
# COMANDO /features
# ==========================================

async def features(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "🤖 Funciones de DarkGPT\n\n"
        "✅ Respuestas en español\n"
        "✅ Programación y código\n"
        "✅ Respuestas progresivas\n"
        "✅ Formato de código\n"
        "✅ Memoria persistente SQLite\n"
        "✅ Historial separado por chat\n"
        "✅ Eliminación del historial\n\n"
        "Se utilizan hasta 12 mensajes "
        "recientes como contexto."
    )


# ==========================================
# COMANDO /memoria
# ==========================================

async def memoria(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        result = await asyncio.to_thread(
            bridge_request,
            "GET",
            "/memory",
            params={
                "chat_id": str(
                    update.effective_chat.id
                )
            }
        )

        count = result.get(
            "messages", 0
        )

        maximum = result.get(
            "max_messages", 12
        )

        await update.message.reply_text(
            "🧠 Memoria de DarkGPT\n\n"
            f"Mensajes guardados: {count}\n"
            f"Máximo de contexto: {maximum}\n\n"
            "El historial se almacena "
            "en tu MacBook.\n\n"
            "Usa /clear o /olvidar "
            "para borrarlo."
        )

    except Exception:
        logger.exception(
            "No se pudo consultar la memoria"
        )

        await update.message.reply_text(
            "❌ No se pudo consultar la memoria.\n"
            "Comprueba que el Bridge "
            "esté actualizado."
        )


# ==========================================
# COMANDOS /clear y /olvidar
# ==========================================

async def clear(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        result = await asyncio.to_thread(
            bridge_request,
            "POST",
            "/memory/clear",
            json={
                "chat_id": str(
                    update.effective_chat.id
                )
            }
        )

        deleted = result.get(
            "deleted", 0
        )

        await update.message.reply_text(
            "🗑️ Memoria eliminada.\n\n"
            f"Mensajes borrados: {deleted}\n\n"
            "Puedes comenzar una "
            "conversación nueva."
        )

    except Exception:
        logger.exception(
            "No se pudo borrar la memoria"
        )

        await update.message.reply_text(
            "❌ No se pudo borrar el historial.\n"
            "Comprueba la conexión "
            "con el Bridge."
        )

# ==========================================
# PARTE 2 DE 4
# FORMATO DE RESPUESTAS
# ==========================================


def format_prose(text: str) -> str:
    """
    Convierte Markdown sencillo a HTML
    compatible con Telegram.
    """

    lines = []

    for line in text.splitlines(keepends=True):

        escaped = html.escape(line)

        # Convertir encabezados Markdown
        escaped = re.sub(
            r"^(\s{0,3})#{1,6}\s+(.+?)(\r?\n)?$",
            lambda m: (
                m.group(1)
                + "<b>"
                + m.group(2)
                + "</b>"
                + (m.group(3) or "")
            ),
            escaped
        )

        # Convertir texto en negritas
        escaped = re.sub(
            r"\*\*(.+?)\*\*",
            r"<b>\1</b>",
            escaped
        )

        # Convertir codigo en linea
        escaped = re.sub(
            r"(?<!`)`([^`\n]+)`(?!`)",
            r"<code>\1</code>",
            escaped
        )

        lines.append(escaped)

    return "".join(lines)


# ==========================================
# DIVIDIR RESPUESTAS LARGAS
# ==========================================

def split_plain(
    text: str,
    limit: int = MAX_TEXT
):
    """
    Divide respuestas largas en fragmentos
    compatibles con Telegram.

    Intenta no cortar palabras.
    """

    while text:

        if len(text) <= limit:
            yield text
            return

        # Buscar un salto de linea
        cut = text.rfind(
            "\n",
            0,
            limit + 1
        )

        # Si no existe, buscar espacio
        if cut <= 0:
            cut = text.rfind(
                " ",
                0,
                limit + 1
            )

        # Si tampoco existe, cortar al limite
        if cut <= 0:
            cut = limit
        else:
            cut += 1

        yield text[:cut]

        text = text[cut:]


# ==========================================
# DETECTAR BLOQUES DE CODIGO
# ==========================================

def extract_ready(
    buffer: str,
    final: bool = False
):
    """
    Separa texto normal y bloques de codigo.

    Evita enviar bloques Markdown
    incompletos mientras Qwen responde.

    Retorna:
        sections: lista de secciones listas
        buffer: texto pendiente
    """

    sections = []

    while buffer:

        opening = FENCE.search(buffer)

        # No hay bloques de codigo
        if not opening:

            if final:

                sections.append(
                    ("prose", buffer)
                )

                buffer = ""

            else:

                last_newline = buffer.rfind(
                    "\n"
                )

                if last_newline >= 0:

                    safe = last_newline + 1

                    sections.append(
                        (
                            "prose",
                            buffer[:safe]
                        )
                    )

                    buffer = buffer[safe:]

            break

        # Texto anterior al bloque de codigo
        if opening.start():

            sections.append(
                (
                    "prose",
                    buffer[:opening.start()]
                )
            )

        buffer = buffer[opening.start():]

        opening = FENCE.match(buffer)

        # Buscar cierre del bloque de codigo
        closing = re.search(
            r"(?m)^[ ]{0,3}```[ \t]*(?:\n|$)",
            buffer[opening.end():]
        )

        # El bloque aun no esta completo
        if closing is None:

            if final:

                sections.append(
                    ("prose", buffer)
                )

                buffer = ""

            break

        code_start = opening.end()

        code_end = (
            code_start
            + closing.start()
        )

        end = (
            code_start
            + closing.end()
        )

        # Agregar codigo completo
        sections.append(
            (
                "code",
                buffer[code_start:code_end]
            )
        )

        closing_text = buffer[code_end:end]

        buffer = (
            (
                "\n"
                if closing_text.endswith("\n")
                else ""
            )
            + buffer[end:]
        )

    return sections, buffer


# ==========================================
# INDICADOR DE ESCRITURA
# ==========================================

async def mantener_escribiendo(
    bot,
    chat_id: int
):
    """
    Muestra 'escribiendo...' en Telegram
    mientras Qwen genera la respuesta.
    """

    try:

        while True:

            try:

                await bot.send_chat_action(
                    chat_id=chat_id,
                    action=ChatAction.TYPING
                )

            except Exception:

                logger.exception(
                    "Error en indicador de escritura"
                )

            # Telegram requiere renovar
            # periodicamente el indicador
            await asyncio.sleep(4)

    except asyncio.CancelledError:
        return

# ==========================================
# PARTE 3 DE 4
# COMUNICACION CON QWEN
# ==========================================


async def deliver_job(
    message,
    status,
    prompt,
    chat_id
):
    """
    Envia una pregunta al Bridge.

    Incluye chat_id para que el Bridge
    utilice la memoria SQLite correcta.

    Recupera los fragmentos generados
    por Qwen y los envia a Telegram.
    """

    # ======================================
    # CREAR TRABAJO EN EL BRIDGE
    # ======================================

    created = await asyncio.to_thread(
        bridge_request,
        "POST",
        "/jobs",
        json={
            "message": prompt,
            "chat_id": str(chat_id)
        }
    )

    job_id = created["job_id"]

    received = 0
    pending = ""
    failures = 0

    started = (
        asyncio.get_running_loop().time()
    )

    last_delivery = started
    delivered = 0

    # ======================================
    # ENVIAR SECCIONES A TELEGRAM
    # ======================================

    async def send_section(kind, text):

        nonlocal delivered, last_delivery

        if not text.strip():
            return

        for piece in split_plain(text):

            if not piece.strip():
                continue

            # Bloques de codigo
            if kind == "code":

                formatted = (
                    "<pre><code>"
                    + html.escape(piece)
                    + "</code></pre>"
                )

            # Texto normal
            else:

                formatted = format_prose(
                    piece
                )

            try:

                await message.reply_text(
                    formatted,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )

            except Exception:

                logger.exception(
                    "Error enviando HTML; "
                    "se usara texto plano"
                )

                await message.reply_text(
                    piece,
                    parse_mode=None,
                    disable_web_page_preview=True
                )

            delivered += 1

            last_delivery = (
                asyncio.get_running_loop().time()
            )

    # ======================================
    # PROCESAR FRAGMENTOS PENDIENTES
    # ======================================

    async def drain(force=False):

        nonlocal pending

        elapsed = (
            asyncio.get_running_loop().time()
            - last_delivery
        )

        # Evita enviar fragmentos demasiado
        # pequenos de manera innecesaria.
        if (
            not force
            and len(pending) < 750
            and (
                not pending
                or elapsed < 12
            )
        ):
            return

        sections, pending = extract_ready(
            pending,
            final=force
        )

        for kind, text in sections:

            await send_section(
                kind,
                text
            )

    # ======================================
    # CONSULTAR EL ESTADO DEL TRABAJO
    # ======================================

    while True:

        elapsed = (
            asyncio.get_running_loop().time()
            - started
        )

        # Tiempo maximo de seguimiento:
        # 20 minutos.
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
                "/jobs/" + job_id
            )

            failures = 0

        except requests.exceptions.RequestException:

            failures += 1

            # Permitir errores temporales
            # de conexion.
            if failures > 10:

                await drain(force=True)
                raise

            await asyncio.sleep(
                min(failures * 2, 15)
            )

            continue

        # ==================================
        # RECIBIR FRAGMENTOS DE QWEN
        # ==================================

        chunks = job.get(
            "chunks"
        ) or []

        if (
            not isinstance(chunks, list)
            or len(chunks) < received
        ):

            raise ValueError(
                "Fragmentos invalidos del Bridge"
            )

        for chunk in chunks[received:]:

            if not isinstance(chunk, str):

                raise ValueError(
                    "Fragmento no valido"
                )

            pending += chunk

        received = len(chunks)

        state = job.get(
            "state"
        )

        finished = state in (
            "done",
            "limit",
            "error"
        )

        await drain(
            force=finished
        )

        # ==================================
        # TRABAJO EN PROCESO
        # ==================================

        if state == "running":
            continue

        # ==================================
        # RESPUESTA COMPLETA
        # ==================================

        if state == "done":

            await status.edit_text(
                "✅ Respuesta terminada.\n"
                f"Mensajes enviados: {delivered}."
            )

            return

        # ==================================
        # LIMITE DE TOKENS
        # ==================================

        if state == "limit":

            await status.edit_text(
                "⚠️ Respuesta incompleta: "
                "Qwen alcanzó el límite de tokens."
            )

            return

        # ==================================
        # ERROR EN EL MODELO
        # ==================================

        if state == "error":

            error = str(
                job.get("error")
                or "Revisa Bridge"
            )[:180]

            await status.edit_text(
                "❌ Generación interrumpida: "
                + error
            )

            return

        raise ValueError(
            "Estado desconocido: "
            + str(state)
        )


# ==========================================
# RECIBIR MENSAJES DE TELEGRAM
# ==========================================

async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """
    Recibe los mensajes del usuario,
    los envia al Bridge y entrega
    la respuesta generada por Qwen.
    """

    message = update.effective_message

    if not message or not message.text:
        return

    # Limite de caracteres permitido
    # por el Bridge.
    if len(message.text) > 4000:

        await message.reply_text(
            "El mensaje supera "
            "los 4000 caracteres."
        )

        return

    # Mensaje de estado
    status = await message.reply_text(
        "⏳ DarkGPT está procesando "
        "tu solicitud…\n"
        "🤖 Qwen2.5 está generando "
        "la respuesta."
    )

    # Indicador de escritura
    typing_task = asyncio.create_task(
        mantener_escribiendo(
            context.bot,
            update.effective_chat.id
        )
    )

    try:

        await deliver_job(
            message,
            status,
            message.text,
            update.effective_chat.id
        )

    # ======================================
    # TIEMPO DE ESPERA
    # ======================================

    except requests.exceptions.Timeout:

        logger.exception(
            "Tiempo de espera agotado"
        )

        await status.edit_text(
            "⏱️ La IA tardó demasiado.\n"
            "Prueba una pregunta más corta."
        )

    # ======================================
    # ERROR HTTP DEL BRIDGE
    # ======================================

    except requests.exceptions.HTTPError as exc:

        code = (
            exc.response.status_code
            if exc.response is not None
            else "?"
        )

        logger.error(
            "Bridge devolvió HTTP %s",
            code
        )

        await status.edit_text(
            "❌ El servidor de IA devolvió "
            f"un error HTTP {code}.\n"
            "Revisa Bridge y llama-server."
        )

    # ======================================
    # ERROR DE CONEXION
    # ======================================

    except (
        requests.exceptions.RequestException,
        ValueError
    ):

        logger.exception(
            "Fallo al consultar Bridge"
        )

        await status.edit_text(
            "🔌 No se pudo consultar "
            "la IA local.\n"
            "Comprueba la MacBook "
            "y el túnel SSH."
        )

    # ======================================
    # ERROR INESPERADO
    # ======================================

    except Exception:

        logger.exception(
            "Error inesperado "
            "procesando mensaje"
        )

        try:

            await status.edit_text(
                "❌ Ocurrió un error "
                "procesando la solicitud.\n"
                "Revisa los logs de Render."
            )

        except Exception:

            logger.exception(
                "No se pudo actualizar "
                "el estado"
            )

    # ======================================
    # FINALIZAR INDICADOR
    # ======================================

    finally:

        typing_task.cancel()

        await typing_task


# ==========================================
# MANEJADOR GENERAL DE ERRORES
# ==========================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):
    """
    Registra los errores inesperados
    recibidos desde Telegram.
    """

    logger.error(
        "Error procesando actualización "
        "de Telegram: %s",
        context.error,
        exc_info=context.error
    )

# ==========================================
# PARTE 4 DE 4
# WEBHOOK, RENDER E INICIO DEL BOT
# ==========================================


async def main():
    """
    Inicia DarkGPT en Render.

    Configura:
    - Variables de entorno
    - Aplicacion de Telegram
    - Comandos
    - Servidor HTTP
    - Webhook
    """

    # ======================================
    # VALIDAR VARIABLES DE ENTORNO
    # ======================================

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

    # ======================================
    # CREAR APLICACION DE TELEGRAM
    # ======================================

    app = (
        Application.builder()
        .token(TOKEN)
        .updater(None)
        .concurrent_updates(True)
        .build()
    )

    # ======================================
    # REGISTRAR COMANDOS
    # ======================================

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

    # ======================================
    # REGISTRAR MENSAJES DE TEXTO
    # ======================================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            message_handler
        )
    )

    # ======================================
    # REGISTRAR MANEJADOR DE ERRORES
    # ======================================

    app.add_error_handler(
        error_handler
    )

    # ======================================
    # SERVIDOR WEB DE RENDER
    # ======================================

    from aiohttp import web

    # Ruta de comprobacion
    async def health(request):

        return web.json_response({
            "status": "ok",
            "bot": "DarkGPT",
            "memory": "SQLite"
        })

    # ======================================
    # RECIBIR WEBHOOK DE TELEGRAM
    # ======================================

    async def webhook(request):

        secret = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token",
            ""
        )

        # Verificar autenticacion
        if not hmac.compare_digest(
            secret,
            WEBHOOK_SECRET
        ):
            return web.Response(
                status=403
            )

        try:

            data = await request.json()

            update = Update.de_json(
                data,
                app.bot
            )

            if update is None:
                return web.Response(
                    status=400
                )

            await app.update_queue.put(
                update
            )

        except (ValueError, TypeError):

            logger.exception(
                "Actualizacion invalida"
            )

            return web.Response(
                status=400
            )

        return web.Response(
            text="OK"
        )

    # ======================================
    # CONFIGURAR RUTAS HTTP
    # ======================================

    server = web.Application(
        client_max_size=1024 * 1024
    )

    server.router.add_get(
        "/",
        health
    )

    server.router.add_get(
        "/health",
        health
    )

    server.router.add_post(
        "/telegram",
        webhook
    )

    # ======================================
    # PREPARAR SERVIDOR
    # ======================================

    runner = web.AppRunner(
        server
    )

    await app.initialize()

    await app.start()

    try:

        await runner.setup()

        site = web.TCPSite(
            runner,
            "0.0.0.0",
            PORT
        )

        await site.start()

        logger.info(
            "Servidor DarkGPT iniciado "
            "en puerto %s",
            PORT
        )

        # ==================================
        # CONFIGURAR WEBHOOK EN TELEGRAM
        # ==================================

        webhook_url = (
            RENDER_EXTERNAL_URL
            + "/telegram"
        )

        await app.bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            allowed_updates=["message"],
            drop_pending_updates=False
        )

        logger.info(
            "Webhook configurado en %s",
            webhook_url
        )

        logger.info(
            "DarkGPT iniciado correctamente"
        )

        logger.info(
            "Memoria gestionada por Bridge SQLite"
        )

        # Mantener servidor funcionando
        await asyncio.Event().wait()

    finally:

        logger.info(
            "Deteniendo DarkGPT"
        )

        await runner.cleanup()

        await app.stop()

        await app.shutdown()


# ==========================================
# PUNTO DE ENTRADA
# ==========================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        logger.info(
            "DarkGPT detenido manualmente"
        )
