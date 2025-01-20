from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from compose_notifications import main
from tests.common import get_event_with_data


@pytest.fixture
def line() -> main.LineInChangeLog:
    return main.LineInChangeLog(
        forum_search_num=1,
        start_time=datetime.now(),
        activities=[1, 2],
        managers='["manager1","manager2"]',
        clickable_name='foo',
        topic_type_id=1,
    )


def test_main():
    # NO SMOKE TEST compose_notifications.main.main
    # TODO paste something to change_log and users
    data = get_event_with_data({'foo': 1, 'triggered_by_func_id': '1'})
    main.main(data, 'context')
    assert True


def test_compose_com_msg_on_new_topic(line: main.LineInChangeLog):
    # NO SMOKE TEST compose_notifications.main.compose_com_msg_on_new_topic
    messages, message, line_ignore = main.compose_com_msg_on_new_topic(line)
    assert 'manager1' in message.managers and 'manager2' in message.managers


def test_enrich_new_record_with_emoji(line: main.LineInChangeLog):
    # NO SMOKE TEST compose_notifications.main.enrich_new_record_with_emoji
    res = main.enrich_new_record_with_emoji(line)
    assert res.topic_emoji
