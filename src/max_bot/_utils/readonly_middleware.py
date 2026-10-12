"""Read-only middleware for the MAX bot.

When emergency read-only mode is on (``EMERGENCY_READONLY_MODE=true``), every update is inspected
before routing: view-only interactions (sub-menus, saved values, ``/start``) pass through, anything
else gets the stub reply and is not handled — so no handler runs and nothing is written.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from maxapi.filters.middleware import BaseMiddleware, HandlerCallable
from maxapi.types.updates import UpdateUnion
from maxapi.types.updates.bot_started import BotStarted
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

from _dependencies.bot.readonly_mode import (
    READONLY_NOTICE,
    READONLY_SAFE_MAX_CMDS,
    READONLY_SAFE_MAX_COMMANDS,
    is_readonly,
)

logger = logging.getLogger(__name__)


def _is_read_safe(event: UpdateUnion) -> bool:
    """Whether this update only shows something (allowed in read-only mode)."""
    if isinstance(event, BotStarted):
        return True
    if isinstance(event, MessageCreated):
        body = event.message.body
        text = (body.text or '').strip() if body is not None else ''
        if not text.startswith('/'):
            return False
        command = text[1:].split()[0].split('@')[0].lower()
        return command in READONLY_SAFE_MAX_COMMANDS
    if isinstance(event, MessageCallback):
        try:
            data = json.loads(event.callback.payload or '')
        except (json.JSONDecodeError, TypeError):
            return False
        return isinstance(data, dict) and data.get('cmd') in READONLY_SAFE_MAX_CMDS
    return False


async def _send_readonly_stub(event: UpdateUnion) -> None:
    """Answer the update with the read-only notice. Sends a message, writes nothing to the DB."""
    try:
        if isinstance(event, MessageCallback):
            await event.ack()
            if event.message is not None:
                await event.edit(text=READONLY_NOTICE)
            elif event.bot is not None:
                await event.bot.send_message(chat_id=event.callback.user.user_id, text=READONLY_NOTICE)
        elif isinstance(event, MessageCreated):
            await event.message.answer(text=READONLY_NOTICE)
    except Exception:
        logger.exception('readonly mode: failed to send the stub')


class ReadonlyMiddleware(BaseMiddleware):
    """Outer middleware that blocks every non-view update while read-only mode is on."""

    async def __call__(self, handler: HandlerCallable, event_object: UpdateUnion, data: dict[str, Any]) -> Any:
        if not is_readonly():
            return await handler(event_object, data)

        if _is_read_safe(event_object):
            return await handler(event_object, data)

        logger.info('readonly mode: blocked update %s', type(event_object).__name__)
        await _send_readonly_stub(event_object)
        return None
