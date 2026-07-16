"""Script send the Debug messages to Admin via special Debug Bot in telegram https://t.me/la_test_1_bot
To receive notifications one should be marked as Admin in PSQL"""

import html

from retry import retry

from _dependencies.bot.messaging import tg_api_service_account
from _dependencies.common.commons import get_app_config, setup_logging
from _dependencies.common.pubsub import Ctx, process_pubsub_message
from _dependencies.common.telegram_message import TelegramMessage

setup_logging(__package__)


@retry(Exception, tries=3, delay=3)
def send_message(admin_user_id: int, message: str) -> None:
    """send individual notification message to telegram (debug)"""

    tg_api = tg_api_service_account()

    # to avoid 4000 symbols restriction for telegram message
    if len(message) > 3500:
        message = message[:1500]

    # Debug messages may contain repr of PTB objects (e.g. ChatType.PRIVATE)
    # wrapped in angle brackets that Telegram would try to parse as HTML.
    # Escape HTML entities to avoid parse errors.
    safe_message = html.escape(message)
    tg_message = TelegramMessage(text=safe_message)
    tg_api.send_message(admin_user_id, tg_message)


def main(event: dict[str, bytes], context: Ctx) -> None:
    """main function, envoked by pub/sub, which sends the notification to Admin"""

    message_from_pubsub = process_pubsub_message(event)

    admin_user_id = get_app_config().my_telegram_id

    send_message(admin_user_id, message_from_pubsub)

    return None
