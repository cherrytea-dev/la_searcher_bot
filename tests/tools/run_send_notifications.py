from functools import wraps
from time import time
from unittest.mock import Mock, patch

from send_notifications.main import main
from tests.common import get_dotenv_config, get_event_with_data
from tests.test_send_notifications import NotSentNotificationFactory


def generate_messages(count: int):
    for i in range(count):
        try:
            content = f'test message {i}'
            NotSentNotificationFactory.create_sync(
                user_id=get_dotenv_config().my_telegram_id,
                message_type='text',
                message_content=content,
                message_text=content,
                message_params='{"parse_mode": "HTML", "reply_markup": {"inline_keyboard": [[{"text": "Смотреть на Карте Поисков", "web_app": {"url": "https://foo"}}]]}, "disable_web_page_preview": "True"}',
            )
            NotSentNotificationFactory.create_sync(
                user_id=get_dotenv_config().my_telegram_id,
                message_content=None,
                message_text=None,
                message_type='coords',
                message_params='{"latitude": "68.970663", "longitude": "33.074918"}',
            )
        except:
            pass


def timed_main():
    main('', '')


if __name__ == '__main__':
    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        patch('_dependencies.pubsub._send_topic'),
        patch('_dependencies.pubsub._get_publisher'),
        patch('_dependencies.pubsub.get_project_id'),
        patch('send_notifications.main.SLEEP_TIME_FOR_NEW_NOTIFS_RECHECK_SECONDS', 0),
    ):
        generate_messages(1)
        context = Mock()
        context.event_id = 123

        event_data = get_event_with_data('foo')
        main(event_data, context)
