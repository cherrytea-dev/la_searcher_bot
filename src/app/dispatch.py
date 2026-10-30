"""Topic → handler registry: the single-container replacement for YMQ triggers.

In the cloud every topic had its own function wired by ``terraform/_func_event_trigger.tf``.
Here the same wiring is a plain dict; handlers are imported lazily (on first message), so a
container that only ever sends notifications never pays for the geocoder imports, and vice
versa.

Handlers keep their cloud signature ``main(event, context)`` and receive the very same event
shape, so not a single line inside the functions had to change.
"""

from __future__ import annotations

import importlib
import json
import logging
from collections.abc import Callable
from typing import Any

from _dependencies.common.pubsub import Topics

#: topic name → dotted path of the function's ``main`` (``<package>.<module>.<callable>``).
TOPIC_HANDLERS: dict[str, str] = {
    Topics.topic_notify_admin.value: 'send_debug_to_admin.main.main',
    Topics.topic_for_first_post_processing.value: 'identify_updates_of_first_posts.main.main',
    Topics.topic_for_notification.value: 'compose_notifications.main.main',
    Topics.topic_to_run_parsing_script.value: 'identify_updates_of_topics.main.main',
    Topics.parse_user_profile_from_forum.value: 'connect_to_forum.main.main',
    Topics.topic_to_send_notifications.value: 'send_notifications.main.main',
    Topics.topic_to_archive_notifs.value: 'archive_notifications.main.main',
}

Handler = Callable[[dict[str, Any], dict[str, Any]], Any]


def build_event(payload: Any) -> dict[str, Any]:
    """Wrap a payload into the Yandex Cloud pub/sub event the handlers expect.

    ``_dependencies.common.yandex_tools.process_pubsub_message_cloud`` reads
    ``event['messages'][0]['details']['message']['body']`` — keep that shape.
    """
    return {
        'messages': [
            {
                'event_metadata': {},
                'details': {
                    'message': {
                        'body': json.dumps(payload),
                    },
                },
            },
        ]
    }


def resolve_handler(topic: str) -> Handler:
    """Import and return the handler of ``topic``."""
    path = TOPIC_HANDLERS.get(topic)
    if path is None:
        raise KeyError(f'no handler registered for topic {topic!r}; known: {sorted(TOPIC_HANDLERS)}')

    module_name, _, attribute = path.rpartition('.')
    module = importlib.import_module(module_name)
    handler = getattr(module, attribute)
    logging.info('resolved handler for topic %s: %s', topic, path)
    return handler  # type: ignore[no-any-return]


def stream_for_topic(topic: str) -> str:
    """Name of the function (its package) serving ``topic`` — the log ``stream_name``."""
    path = TOPIC_HANDLERS.get(topic)
    return path.split('.', 1)[0] if path else 'unknown'


def known_topics() -> list[str]:
    return sorted(TOPIC_HANDLERS)
