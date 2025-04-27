from functools import lru_cache, wraps
from time import time
from unittest.mock import patch

from dotenv import load_dotenv

from _dependencies.commons import AppConfig
from send_notifications.main import main
from tests.test_send_notifications import NotSentNotificationFactory


@lru_cache
def get_dotenv_config() -> AppConfig:
    assert load_dotenv('.env', override=True)
    return AppConfig()


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


def timing(f):
    @wraps(f)
    def wrap(*args, **kw):
        ts = time()
        result = f(*args, **kw)
        te = time()
        print('func:%r args:[%r, %r] took: %2.4f sec' % (f.__name__, args, kw, te - ts))
        return result

    return wrap


@timing
def timed_main():
    main('', '')


if __name__ == '__main__':
    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        patch('_dependencies.commons.get_publisher'),
        patch('_dependencies.commons.get_project_id'),
        patch('_dependencies.commons._send_topic'),
        patch('send_notifications.main.SLEEP_TIME_FOR_NEW_NOTIFS_RECHECK_SECONDS', 0),
    ):
        generate_messages(1)

        timed_main()
