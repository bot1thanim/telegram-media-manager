"""
app/telegram/webhook_server.py
================================
Webhook endpoint and /health endpoint.
- POST /webhook  — receives Telegram updates, validates secret token (SRS §6.3)
- GET  /health   — returns 200 OK for Render health checks (SRS §4.3)
"""

import hashlib
import hmac
import json
import logging

from aiohttp import web
from telegram import Update
from telegram.ext import Application

logger = logging.getLogger(__name__)


async def health_handler(request: web.Request) -> web.Response:
    """
    GET /health
    Returns 200 OK with a simple JSON body.
    Used by Render health checks and keep-alive pings.
    """
    return web.json_response({"status": "ok"})


async def webhook_handler(request: web.Request) -> web.Response:
    """
    POST /webhook
    Validates the X-Telegram-Bot-Api-Secret-Token header,
    then passes the update to the PTB Application.
    """
    application: Application = request.app["ptb_application"]
    secret_token: str = request.app["webhook_secret_token"]

    # --- Validate secret token (SRS §6.3) ---
    incoming_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(incoming_token, secret_token):
        logger.warning(
            "Webhook request rejected: invalid secret token from %s",
            request.remote,
        )
        return web.Response(status=403, text="Forbidden")

    # --- Parse and dispatch update ---
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as exc:
        logger.exception("Error processing webhook update: %s", exc)
        # Return 200 to Telegram anyway — otherwise it will retry indefinitely
        return web.Response(status=200, text="Error processed")

    return web.Response(status=200, text="OK")


def build_aiohttp_app(
    ptb_application: Application,
    webhook_secret_token: str,
    webhook_path: str = "/webhook",
) -> web.Application:
    """
    Build and return the aiohttp web application with routes registered.
    """
    app = web.Application()
    app["ptb_application"] = ptb_application
    app["webhook_secret_token"] = webhook_secret_token

    app.router.add_get("/health", health_handler)
    app.router.add_post(webhook_path, webhook_handler)

    return app
