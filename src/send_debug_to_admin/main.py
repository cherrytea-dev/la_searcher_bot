"""Script send the Debug messages to Admin via special Debug Bot in telegram https://t.me/la_test_1_bot
To receive notifications one should be marked as Admin in PSQL"""

import base64
import logging

from google.cloud.functions.context import Context
from retry import retry

from _dependencies.commons import get_app_config, setup_google_logging
from _dependencies.misc import process_pubsub_message_v2, tg_api_service_account

setup_google_logging()


@retry(Exception, tries=3, delay=3)
def send_message(admin_user_id: int, message: str) -> None:
    """send individual notification message to telegram (debug)"""

    tg_api = tg_api_service_account()

    # to avoid 4000 symbols restriction for telegram message
    if len(message) > 3500:
        message = message[:1500]

    params = {'chat_id': admin_user_id, 'text': message}
    tg_api.send_message(params)


def main(event: dict[str, bytes], context: Context) -> None:
    """main function, envoked by pub/sub, which sends the notification to Admin"""

    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    logging.info(f'[send_debug]: received from pubsub: {pubsub_message}')

    message_from_pubsub = process_pubsub_message_v2(event)

    admin_user_id = get_app_config().my_telegram_id

    send_message(admin_user_id, message_from_pubsub)

    return None
