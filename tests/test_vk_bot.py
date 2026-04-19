import datetime
from contextlib import suppress
from random import randint
from unittest.mock import MagicMock, patch

import pytest
from polyfactory.factories import DataclassFactory
from sqlalchemy.engine import Connection

from _dependencies.vk_api import VKApi
from tests.common import find_model, get_event_with_data
from tests.factories.db_factories import NotifByUserFactory, UserFactory, get_session
from tests.factories.db_models import User
from vk_bot import main
from vk_bot._utils import bot_polling


@pytest.fixture(scope='session')
def db_client():
    yield main.db()


@pytest.mark.parametrize(
    'msg, tg_id, hash',
    [
        # Valid cases (should return integer)
        ('telegram_id: 12345 invite_hash: 3C129A6HD', 12345, '3C129A6HD'),
        ('Telegram_Id: 67890 invite_hash: ABC123', 67890, 'ABC123'),
        # Invalid cases (should return None)
        ('invite_hash: ABC123', None, None),
        ('telegram_id: abc invite_hash: XYZ', None, None),
        ('telegram_id:', None, None),
        ('telegram_id: -123', None, None),
        ('no match here', None, None),
        ('telegram_id:  ', None, None),
        ('', None, None),
    ],
)
def test_receive_message_ok(msg: str, tg_id: int, hash: str):
    assert bot_polling.get_invite_from_message(msg) == (tg_id, hash)
