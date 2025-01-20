from unittest.mock import patch

import pytest
from google.cloud import bigquery
from telegram import Bot
from telegram.ext import ExtBot

from archive_to_bigquery import main
from tests.common import get_event_with_data


@pytest.fixture
def patch_big_query():
    with (
        # patch.object(bigquery.Client, '__init__', MagicMock(return_value=None)),
        patch.object(bigquery, 'Client'),
    ):
        yield


def test_main(patch_big_query):
    # NO SMOKE TEST archive_to_bigquery.main.main
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
