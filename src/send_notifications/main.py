"""Entry point for send_notifications — triggerable via pub/sub."""

import datetime
import logging

from _dependencies.bot.messaging import tg_api_main_account
from _dependencies.bot.messenger_clients import MaxClient
from _dependencies.bot.vk_api_client import get_default_vk_api_client
from _dependencies.common.commons import setup_logging, sqlalchemy_get_pool
from _dependencies.common.lock_manager import FunctionLockError, lock_manager
from _dependencies.common.misc import generate_random_function_id
from _dependencies.common.pubsub import Ctx
from send_notifications._utils.clients.max_notificator import MaxNotificator
from send_notifications._utils.clients.telegram_notificator import TelegramNotificator
from send_notifications._utils.clients.vk_notificator import VKNotificator
from send_notifications._utils.database import DBClient
from send_notifications._utils.helpers import FUNC_NAME, INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS
from send_notifications._utils.models import TimeAnalytics
from send_notifications._utils.services.notification_sender import NotificationSender


def main(event: dict, context: Ctx) -> str | None:
    """Send the prepared notifications to users via Telegram, VK, and MAX."""
    setup_logging(__package__)

    db_client = DBClient()
    vk_api = get_default_vk_api_client()
    tg_api = tg_api_main_account()

    with MaxClient() as max_client:
        sender = NotificationSender(
            db_client=db_client,
            vk_notificator=VKNotificator(vk_api),
            tg_notificator=TelegramNotificator(tg_api),
            max_notificator=MaxNotificator(max_client),
        )

        time_analytics = TimeAnalytics(script_start_time=datetime.datetime.now())
        function_id = generate_random_function_id()
        engine = sqlalchemy_get_pool()

        try:
            with lock_manager(engine, FUNC_NAME, INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS):
                changed_ids = sender.send_all(function_id, time_analytics)
        except FunctionLockError:
            logging.info('script cancelled')
            return None

        sender.finish_analytics(time_analytics, changed_ids)
        logging.info('script finished')
        return 'ok'
