from datetime import datetime
from random import randint
from typing import NamedTuple
from unittest.mock import MagicMock, patch

import pytest
from telegram import Bot
from telegram.ext import ExtBot

from manage_topics import main
from tests.common import get_event_with_data
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

        change_log_id = main.save_status_for_topic(topic_id, new_status)

        updated_search: Search = get_session().query(Search).filter_by(search_forum_num=topic_id).first()
        assert updated_search.status == new_status

        change_log: ChangeLog = get_session().query(ChangeLog).filter_by(id=change_log_id).first()
        assert change_log is not None
        assert change_log.search_forum_num == topic_id
        assert change_log.changed_field == 'status_change'
        assert change_log.new_value == new_status
        assert change_log.change_type == 1

    def test_save_existing_status(self, topic_id: int):
        existing_status = 'existing_status'
        SearchFactory.create_sync(search_forum_num=topic_id, status=existing_status)

        change_log_id = main.save_status_for_topic(topic_id, existing_status)

        assert change_log_id is None

        search: Search = get_session().query(Search).filter_by(search_forum_num=topic_id).first()
        assert search.status == existing_status

        change_log_count = get_session().query(ChangeLog).filter_by(search_forum_num=topic_id).count()
        assert change_log_count == 0

    def test_save_status_for_nonexistent_topic(self, topic_id: int):
        new_status = 'new_status'
        search = SearchFactory.create_sync(search_forum_num=topic_id)

        change_log_id = main.save_status_for_topic(topic_id, new_status)

        assert change_log_id is not None

        search: Search = get_session().query(Search).filter_by(search_forum_num=topic_id).first()
        assert search is not None
        assert search.status == new_status

        change_log: ChangeLog = get_session().query(ChangeLog).filter_by(id=change_log_id).first()
        assert change_log is not None
        assert change_log.search_forum_num == topic_id
        assert change_log.changed_field == 'status_change'
        assert change_log.new_value == new_status
        assert change_log.change_type == 1
