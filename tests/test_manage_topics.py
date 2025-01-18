from unittest.mock import patch

from telegram import Bot
from telegram.ext import ExtBot

from manage_topics import main
from tests.common import get_event_with_data


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
        main.main(event, 'context')
        assert True
        # TODO assert that event was published
        # TODO check record in table `change_log`
