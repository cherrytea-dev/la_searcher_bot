"""Entry point for send_notifications — triggerable via pub/sub."""

import datetime
import logging

from _dependencies.bot.messaging import tg_api_main_account
from _dependencies.bot.messenger_clients import MaxClient
from _dependencies.bot.vk_api_client import get_default_vk_api_client
from _dependencies.common.commons import get_app_config, setup_logging, sqlalchemy_get_pool
from _dependencies.common.lock_manager import FunctionLockError, lock_manager
from _dependencies.common.misc import generate_random_function_id
from _dependencies.common.pubsub import Ctx
from send_notifications._utils.clients.max_notificator import MaxNotificator
from send_notifications._utils.clients.telegram_notificator import TelegramNotificator
from send_notifications._utils.clients.vk_notificator import VKNotificator
from send_notifications._utils.database import DBClient
from send_notifications._utils.helpers import FUNC_NAME
from send_notifications._utils.models import TimeAnalytics
from send_notifications._utils.services.notification_sender import NotificationSender


def _run_sender(sender: NotificationSender) -> str | None:
    """Read, send and track notifications (shared by the MAX and no-MAX paths)."""

    time_analytics = TimeAnalytics(script_start_time=datetime.datetime.now())
    function_id = generate_random_function_id()
    engine = sqlalchemy_get_pool()

    try:
        with lock_manager(engine, FUNC_NAME):
            changed_ids = sender.send_all(function_id, time_analytics)
    except FunctionLockError:
        logging.info('script cancelled')
        return None

    sender.finish_analytics(time_analytics, changed_ids)
    logging.info('script finished')
    return 'ok'


def main(event: dict, context: Ctx) -> str | None:
    """Send the prepared notifications to users via Telegram, VK, and MAX."""
    setup_logging(__package__)

    db_client = DBClient()
    vk_api = get_default_vk_api_client()
    tg_api = tg_api_main_account()

    def build_sender(max_notificator: MaxNotificator) -> NotificationSender:
        return NotificationSender(
            db_client=db_client,
            vk_notificator=VKNotificator(vk_api),
            tg_notificator=TelegramNotificator(tg_api),
            max_notificator=max_notificator,
        )

    # MAX is optional: without MAX_BOT_TOKEN we skip its client entirely, otherwise
    # MaxBot() raises InvalidToken and the whole handler (Telegram/VK included) dies.
    if get_app_config().max_bot_token:
        with MaxClient() as max_client:
            return _run_sender(build_sender(MaxNotificator(max_client)))

    return _run_sender(build_sender(MaxNotificator(None)))
