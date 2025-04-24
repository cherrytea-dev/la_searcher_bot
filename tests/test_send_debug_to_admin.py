from unittest.mock import Mock, patch

import pytest

from _dependencies.telegram_api_wrapper import TGApiBase
from send_debug_to_admin import main
from tests.common import get_event_with_data


@pytest.fixture(autouse=True)
def mock_send_message() -> Mock:
    # TODO get list of sent messages
    with patch.object(TGApiBase, '_make_api_call') as mock:
        yield mock


@pytest.mark.parametrize(
    'message',
    [
        'some text',
        "'Somebody._\ud83c\udfa9', 'username': =Chat(first_name='\u0410\u043d\u0434\u0440\u0435\u0439', ",
    ],
)
def test_main_positive(mock_send_message, message: str):
    message_text = ''
    event = get_event_with_data(message_text)

    main.main(event, 'context')
    mock_send_message.assert_called_once()
