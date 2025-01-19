from unittest.mock import AsyncMock, Mock, patch

from _dependencies import misc
from tests.common import get_test_config


def test_notify_admin(patch_pubsub_client, bot_mock_send_message: AsyncMock):
    data = 'some message'

    misc.notify_admin(data)
    bot_mock_send_message.assert_called_once_with(chat_id=get_test_config().my_telegram_id, text=data)


def test_make_api_call():
    # TODO mock requests
    misc.make_api_call('test', {'a: 1'})
