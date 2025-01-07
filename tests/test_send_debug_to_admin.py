import base64
from unittest.mock import patch, AsyncMock

import pytest
from telegram.ext import ExtBot
from telegram import Bot

from tests.common import emulated_get_secrets, get_config


@pytest.fixture
def autopatch_secrets(common_patches):
    with patch("send_debug_to_admin.main.get_secrets", emulated_get_secrets):
        yield


def test_main_positive(autopatch_secrets):
    from send_debug_to_admin.main import main

    message_text = "some text"
    data = base64.b64encode(str({"data": {"message": message_text}}).encode())
    event = {"data": data}

    with (
        patch.object(ExtBot, "send_message") as mock_send_message,
        patch.object(Bot, "get_me"),
    ):
        main(event, "context")
        mock_send_message.assert_called_once_with(
            chat_id=get_config().my_telegram_id,
            text=message_text,
        )


def test_main_with_exception(autopatch_secrets):
    from send_debug_to_admin.main import main

    message_text = "some text"
    data = base64.b64encode(str({"data": {"message": message_text}}).encode())
    event = {"data": data}

    with (
        patch.object(ExtBot, "send_message") as mock_send_message,
        patch.object(Bot, "get_me", AsyncMock(side_effect=[Exception, None])),
    ):
        main(event, "context")
        mock_send_message.assert_called_once()
        assert "ERROR" in mock_send_message.call_args[1]["text"]
