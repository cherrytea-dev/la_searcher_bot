"""Script send the Debug messages to Admin via special Debug Bot in telegram https://t.me/la_test_1_bot
To receive notifications one should be marked as Admin in PSQL"""

import base64
import datetime
import logging
from typing import Any, Optional

from _dependencies.commons import get_app_config, setup_google_logging
from _dependencies.misc import process_pubsub_message_v2, process_sending_message_async_other_bot

setup_google_logging()

logging.getLogger('telegram.vendor.ptb_urllib3.urllib3').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


def send_message(admin_user_id, message):
    """send individual notification message to telegram (debug)"""

    try:
        # to avoid 4000 symbols restriction for telegram message
        if len(message) > 3500:
            message = message[:1500]

        data = {'text': message}
        process_sending_message_async_other_bot(user_id=admin_user_id, data=data)

    except Exception as e:
        logging.info('[send_debug]: send debug to telegram failed')
        logging.exception(e)

        try:
            debug_message = f'ERROR! {datetime.datetime.now()}: {e}'

            data = {'text': debug_message}
            process_sending_message_async_other_bot(user_id=admin_user_id, data=data)

        except Exception as e2:
            logging.exception(e2)

    return None


def main(event, context):  # noqa
    """main function, envoked by pub/sub, which sends the notification to Admin"""  # noqa

    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    logging.info('[send_debug]: received from pubsub: {}'.format(pubsub_message))  # noqa

    message_from_pubsub = process_pubsub_message_v2(event)

    admin_user_id = get_app_config().my_telegram_id

    send_message(admin_user_id, message_from_pubsub)

    return None
