"""Tests for the topic → handler registry that replaces the YMQ triggers (:mod:`app.dispatch`)."""

from __future__ import annotations

import pytest

from _dependencies.common.pubsub import Topics, process_pubsub_message
from app.dispatch import TOPIC_HANDLERS, build_event, known_topics, resolve_handler


def test_every_topic_has_a_handler() -> None:
    """A topic without a handler would silently swallow messages."""
    assert {topic.value for topic in Topics} == set(TOPIC_HANDLERS)


@pytest.mark.parametrize(
    'payload',
    [
        {'triggered_by_func_id': 1, 'text': 'compose notifications'},
        [1, 2, 3],
        [['folder', 'extra']],
        'go',
    ],
)
def test_build_event_round_trips_through_process_pubsub_message(payload: object) -> None:
    assert process_pubsub_message(build_event(payload)) == payload


def test_resolve_handler_imports_the_function_lazily() -> None:
    handler = resolve_handler(Topics.topic_notify_admin.value)

    assert callable(handler)
    assert handler.__name__ == 'main'


def test_unknown_topic_is_rejected() -> None:
    with pytest.raises(KeyError):
        resolve_handler('topic_that_does_not_exist')


@pytest.mark.parametrize('topic', sorted(TOPIC_HANDLERS))
def test_every_registered_path_points_at_a_real_callable(topic: str) -> None:
    """A typo in the registry would otherwise surface only in production."""
    handler = resolve_handler(topic)

    assert callable(handler)
    assert handler.__name__ == 'main'


def test_known_topics_are_sorted() -> None:
    topics = known_topics()

    assert topics == sorted(topics)
    assert len(topics) == len(Topics)
