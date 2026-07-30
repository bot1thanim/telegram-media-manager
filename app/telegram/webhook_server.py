"""Validated aiohttp webhook and health endpoints for the Telegram application."""

from __future__ import annotations

import hmac
import json
import logging

from aiohttp import web
from telegram import Update
from telegram.ext import Application

logger = logging.getLogger(__name__)
MAX_WEBHOOK_BODY_BYTES = 1_048_576


async def health_handler(request: web.Request) -> web.Response:
    """Return the lightweight liveness endpoint required by Render."""
    del request
    return web.json_response({"status": "ok"})


async def webhook_handler(request: web.Request) -> web.Response:
    """Authenticate, validate and synchronously dispatch a Telegram update."""
    application: Application = request.app["ptb_application"]
    secret_token: str = request.app["webhook_secret_token"]
    incoming_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(incoming_token, secret_token):
        logger.warning(
            "Webhook request rejected: invalid secret token from %s", request.remote
        )
        return web.Response(status=403, text="Forbidden")

    try:
        data = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, web.HTTPException):
        logger.warning("Webhook request rejected: invalid JSON from %s", request.remote)
        return web.Response(status=400, text="Invalid JSON")
    if not isinstance(data, dict) or not isinstance(data.get("update_id"), int):
        return web.Response(status=400, text="Invalid update")

    try:
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception:
        logger.exception("Error processing webhook update %s", data["update_id"])
        # A 5xx response asks Telegram to retry the update.  Downstream handlers
        # are idempotent and database constraints provide durable de-duplication.
        return web.Response(status=500, text="Temporary processing failure")
    return web.Response(status=200, text="OK")


def build_aiohttp_app(
    ptb_application: Application,
    webhook_secret_token: str,
    webhook_path: str = "/webhook",
) -> web.Application:
    """Build the bounded HTTP application used by the Render web service."""
    app = web.Application(client_max_size=MAX_WEBHOOK_BODY_BYTES)
    app["ptb_application"] = ptb_application
    app["webhook_secret_token"] = webhook_secret_token
    app.router.add_get("/health", health_handler)
    app.router.add_post(webhook_path, webhook_handler)
    return app
