"""Script send the Debug messages to Admin via special Debug Bot in telegram https://t.me/la_test_1_bot
To receive notifications one should be marked as Admin in PSQL"""

from retry import retry

from _dependencies.commons import get_app_config, setup_logging
from _dependencies.misc import tg_api_service_account
from _dependencies.pubsub import Ctx, process_pubsub_message

setup_logging()


@retry(Exception, tries=3, delay=3)
def send_message(admin_user_id: int, message: str) -> None:
    """send individual notification message to telegram (debug)"""

    tg_api = tg_api_service_account()

    # to avoid 4000 symbols restriction for telegram message
    if len(message) > 3500:
        message = message[:1500]

    params = {'chat_id': admin_user_id, 'text': message}
    tg_api.send_message(params)


def main(event: dict[str, bytes], context: Ctx) -> None:
    """main function, envoked by pub/sub, which sends the notification to Admin"""

    message_from_pubsub = process_pubsub_message(event)

    admin_user_id = get_app_config().my_telegram_id

    send_message(admin_user_id, message_from_pubsub)

    return None
