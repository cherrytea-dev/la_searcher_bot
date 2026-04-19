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
from vk_bot import bot_polling, main


@pytest.fixture(scope='session')
def db_client():
    yield main.db()


@pytest.mark.parametrize(
    'msg, tg_id',
    [
        # Valid cases (should return integer)
        ('telegram_id: 12345 invite_hash: 3C129A6HD', 12345),
        ('Telegram_Id: 67890 invite_hash: ABC123', 67890),
        ('telegram_id:   42   invite_hash: XYZ', 42),
        ('telegram_id: 999', 999),
        ('Please connect telegram_id: 777 invite_hash: DEF456 thanks', 777),
        ('telegram_id: 555\ninvite_hash: GHI789', 555),
        # Edge valid cases
        ('telegram_id: 0', 0),
        ('telegram_id: 12345', 12345),
        ('TELEGRAM_ID: 888', 888),
        ('Telegram_id: 111 invite_hash: something', 111),
        ('some prefix telegram_id: 222 some suffix', 222),
        ('telegram_id: 333 invite_hash: ABC', 333),
        # Invalid cases (should return None)
        ('invite_hash: ABC123', None),
        ('telegram_id: abc invite_hash: XYZ', None),
        ('', None),
        ('telegram_id:', None),
        ('telegram_id: -123', None),
        ('no match here', None),
        ('telegram_id:  ', None),
        ('telegram_id: 123 456', 123),  # regex will match first number
    ],
)
def test_receive_message_ok(msg: str, tg_id: int):
    assert bot_polling.get_invite_from_message(msg) == tg_id
