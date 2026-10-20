import pytest

from vk_bot import main
from vk_bot._utils import bot_polling


@pytest.fixture(scope='session')
def db_client():
    yield main.db()


def test_parse_event():
    json_ = {
        'group_id': 237036024,
        'type': 'message_new',
        'event_id': 'b1dce60000000000924',
        'v': '5.199',
        'object': {
            'client_info': {
                'button_actions': [
                    'text',
                    'vkpay',
                    'open_app',
                    'location',
                    'open_link',
                    'open_photo',
                    'callback',
                    'intent_subscribe',
                    'intent_unsubscribe',
                ],
                'keyboard': True,
                'inline_keyboard': True,
                'carousel': True,
                'lang_id': 0,
            },
            'message': {
                'date': 1776686903,
                'from_id': 1234567,
                'id': 7492,
                'version': 10008319,
                'out': 0,
                'fwd_messages': [],
                'important': False,
                'is_hidden': False,
                'attachments': [],
                'conversation_message_id': 4854,
                'text': 'foo',
                'peer_id': 1234567,
                'random_id': 0,
            },
        },
    }

    event = bot_polling.UpdateEvent.model_validate(json_)
    assert event.object.message.text == 'foo'
