"""Yandex Cloud Function entry point for the MAX bot.

This function is triggered by an HTTP gateway (Yandex API Gateway)
that forwards MAX Callback API webhook events.

Uses ``maxapi.Dispatcher.handle()`` to process incoming events
(the same dispatch logic as long-polling mode in ``bot_polling.py``).

The ``Bot`` and ``Dispatcher`` are created once at module level and
reused across warm invocations. ``Dispatcher.startup()`` is called
once (it's idempotent — the ``_ready`` flag prevents re-initialization).

Secret verification: The ``X-Max-Bot-Api-Secret`` header is checked
against ``MAX_BOT_WEBHOOK_SECRET`` env var using constant-time comparison.
"""

import asyncio
import logging
import secrets

from maxapi import Bot, Dispatcher
from maxapi.methods.types.getted_updates import process_update_webhook

from _dependencies.common.commons import AppConfig, get_app_config, setup_logging
from _dependencies.common.misc import (
    RequestWrapper,
    ResponseWrapper,
    request_response_converter,
)

from ._utils import handlers

setup_logging(__package__)

logger = logging.getLogger(__name__)

# ─── Module-level lazy init ────────────────────────────────────────────────

_bot: Bot | None = None
_dp: Dispatcher | None = None
_initialized = False


async def _init_dispatcher() -> None:
    """Create ``Bot``, ``Dispatcher``, register handlers, and start up once."""
    global _bot, _dp, _initialized  # noqa: PLW0603

    if _initialized:
        return

    _bot = Bot()
    _dp = Dispatcher()
    _dp.include_routers(handlers.router)
    handlers.set_fsm(_dp.fsm)

    await _dp.startup(_bot)
    _initialized = True
    logger.info('MAX bot dispatcher initialized (webhook mode)')


async def _handle_webhook_async(event_json: dict) -> None:
    """Parse and dispatch a single webhook event."""
    if _dp is None or _bot is None:
        logger.error('Dispatcher not initialized')
        return

    event_object = await process_update_webhook(event_json=event_json, bot=_bot)
    if event_object is None:
        logger.warning('Unknown update type: %s', event_json.get('update_type'))
        return

    await _dp.handle(event_object)


# ─── Yandex Cloud Function entry point ─────────────────────────────────────


@request_response_converter
def main(request: RequestWrapper, *args: object, **kwargs: object) -> ResponseWrapper:
    """Handle incoming MAX webhook event.

    Verifies the ``X-Max-Bot-Api-Secret`` header, parses the JSON payload,
    and dispatches the event to the appropriate handler.

    Returns ``"ok"`` with status 200 on success, or an error status code.
    """
    logger.info('Incoming MAX webhook request: method=%s', request.method)

    # ── Verify webhook secret ──────────────────────────────────────────
    config: AppConfig = get_app_config()
    expected_secret = config.max_bot_webhook_secret

    if expected_secret:
        actual_secret = request.headers.get('X-Max-Bot-Api-Secret', '')
        if not actual_secret or not secrets.compare_digest(actual_secret, expected_secret):
            logger.warning('Invalid or missing X-Max-Bot-Api-Secret header')
            return ResponseWrapper(data='Forbidden', status_code=403)

    # ── Parse event JSON ───────────────────────────────────────────────
    event_json = request.json_
    if not event_json:
        logger.warning('Empty request body')
        return ResponseWrapper(data='Bad Request', status_code=400)

    # ── Dispatch event ─────────────────────────────────────────────────
    try:
        asyncio.run(_init_dispatcher())
        asyncio.run(_handle_webhook_async(event_json))
    except Exception:
        logger.exception('Error processing MAX webhook event')
        return ResponseWrapper(data='Internal Server Error', status_code=500)

    return ResponseWrapper(data='ok', status_code=200)
