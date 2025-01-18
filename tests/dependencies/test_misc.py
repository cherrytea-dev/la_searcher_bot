from unittest.mock import Mock, patch

from telegram import Bot
from telegram.ext import ExtBot

from _dependencies import misc
from tests.common import get_test_config


def test_notify_admin(patch_pubsub_client):
    data = 'some message'

    with (
        patch.object(ExtBot, 'send_message') as mock,
        patch.object(Bot, 'get_me'),
    ):
        misc.notify_admin(data)
    mock.assert_called_once_with(chat_id=get_test_config().my_telegram_id, text=data)


def test_make_api_call():
    # TODO mock requests
    misc.make_api_call('test', {'a: 1'})
