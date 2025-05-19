from datetime import datetime
from random import randint
from typing import NamedTuple
from unittest.mock import MagicMock, patch

import pytest
from telegram import Bot
from telegram.ext import ExtBot

from _dependencies.topic_management import save_status_for_topic
from manage_topics import main
from tests.common import find_model, get_event_with_data
from tests.factories.db_factories import SearchFactory, get_session
from tests.factories.db_models import ChangeLog, Search


class Context(NamedTuple):
    event_id: int


def test_main():
    event = get_event_with_data(
        {
            'topic_id': 123,
            'visibility': True,
            'status': 'on',
        }
    )

    with (
        patch.object(ExtBot, 'send_message'),
        patch.object(Bot, 'get_me'),
    ):
        main.main(event, Context(event_id=123))
        assert True


@pytest.fixture
def topic_id() -> int:
    return randint(1, 1_000_000)


class TestSaveStatusForTopic:
    def test_save_new_status(self, topic_id: int):
        SearchFactory.create_sync(search_forum_num=topic_id, status='old_status')
        new_status = 'new_status'

        pool = main.sql_connect()
        with pool.connect() as conn:
            change_log_id = save_status_for_topic(conn, topic_id, new_status)

        assert find_model(get_session(), Search, search_forum_num=topic_id, status=new_status)

        change_log = find_model(get_session(), ChangeLog, id=change_log_id)

        assert change_log.search_forum_num == topic_id
        assert change_log.changed_field == 'status_change'
        assert change_log.new_value == new_status
        assert change_log.change_type == 1

    def test_save_existing_status(self, topic_id: int):
        existing_status = 'existing_status'
        SearchFactory.create_sync(search_forum_num=topic_id, status=existing_status)

        pool = main.sql_connect()
        with pool.connect() as conn:
            change_log_id = save_status_for_topic(conn, topic_id, existing_status)

        assert change_log_id is None

        assert find_model(get_session(), Search, search_forum_num=topic_id, status=existing_status)

        change_log_count = get_session().query(ChangeLog).filter_by(search_forum_num=topic_id).count()
        assert change_log_count == 0

    def test_save_status_for_nonexistent_topic(self, topic_id: int):
        new_status = 'new_status'
        SearchFactory.create_sync(search_forum_num=topic_id)

        pool = main.sql_connect()
        with pool.connect() as conn:
            change_log_id = save_status_for_topic(conn, topic_id, new_status)

        assert change_log_id is not None

        assert find_model(get_session(), Search, search_forum_num=topic_id, status=new_status)

        change_log = find_model(get_session(), ChangeLog, id=change_log_id)
        assert change_log.search_forum_num == topic_id
        assert change_log.changed_field == 'status_change'
        assert change_log.new_value == new_status
        assert change_log.change_type == 1
