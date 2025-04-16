import logging

from telegram import Update

from _dependencies.misc import notify_admin

from ..buttons import CoordinateSettingsMenu, b_back_to_start, b_menu_set_region
from ..common import (
    HandlerResult,
    UpdateBasicParams,
    UpdateExtraParams,
    create_one_column_reply_markup,
    generate_yandex_maps_place_link,
)
from ..database import db
from ..message_sending import tg_api


def handle_user_geolocation(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    """process coordinates which user sent to bot"""

    db().save_user_coordinates(update_params.user_id, update_params.user_latitude, update_params.user_longitude)

    bot_message = 'Ваши "домашние координаты" сохранены:\n'
    bot_message += generate_yandex_maps_place_link(update_params.user_latitude, update_params.user_longitude, 'coords')
    bot_message += (
        '\nТеперь для всех поисков, где удастся распознать координаты штаба или '
        'населенного пункта, будет указываться направление и расстояние по '
        'прямой от ваших "домашних координат".'
    )
    keyboard_settings = [
        CoordinateSettingsMenu.b_coords_check,
        CoordinateSettingsMenu.b_coords_del,
        b_back_to_start,
    ]

    return bot_message, create_one_column_reply_markup(keyboard_settings)


def handle_force_user_to_set_region(user_id: int) -> HandlerResult:
    logging.info(f'user {user_id} is forced to fill in the region')
    bot_message = (
        'Для корректной работы бота, пожалуйста, задайте свой регион. Для этого '
        'с помощью кнопок меню выберите сначала ФО (федеральный округ), а затем и '
        'регион. Можно выбирать несколько регионов из разных ФО. Выбор региона '
        'также можно отменить, повторно нажав на кнопку с названием региона. '
        'Функционал бота не будет активирован, пока не выбран хотя бы один регион.'
    )

    return bot_message, create_one_column_reply_markup([b_menu_set_region])


def process_unneeded_messages(update: Update, update_params: UpdateBasicParams) -> bool:
    """process messages which are not a part of designed dialogue"""

    user_id = update_params.user_id
    # CASE 2 – when user changed auto-delete setting in the bot
    if update_params.timer_changed:
        logging.info('user changed auto-delete timer settings')
        return True

    # CASE 3 – when user sends a PHOTO or attached DOCUMENT or VOICE message
    if update_params.photo or update_params.document or update_params.voice or update_params.sticker:
        logging.debug('user sends photos to bot')

        bot_message = (
            'Спасибо, интересное! Однако, бот работает только с текстовыми командами. '
            'Пожалуйста, воспользуйтесь текстовыми кнопками бота, находящимися на '
            'месте обычной клавиатуры телеграм.'
        )
        data = {'text': bot_message, 'chat_id': user_id}
        tg_api().send_message(data)
        return True

    # CASE 4 – when some Channel writes to bot
    if update_params.channel_type and user_id < 0:
        notify_admin('[comm]: INFO: CHANNEL sends messages to bot!')

        try:
            tg_api().leave_chat(user_id)
            notify_admin(f'[comm]: INFO: we have left the CHANNEL {user_id}')

        except Exception:
            logging.exception(f'[comm]: Leaving channel was not successful: {user_id}')
            notify_admin(f'[comm]: Leaving channel was not successful: {user_id}')
        return True

    # CASE 5 – when user sends Contact
    if update_params.contact:
        bot_message = (
            'Спасибо, буду знать. Вот только бот не работает с контактами и отвечает '
            'только на определенные текстовые команды.'
        )
        data = {'text': bot_message, 'chat_id': user_id}
        tg_api().send_message(data)
        return True

    # CASE 6 – when user mentions bot as @LizaAlert_Searcher_Bot in another telegram chat. Bot should do nothing
    if update_params.inline_query:
        notify_admin('[comm]: User mentioned bot in some chats')
        logging.info(f'bot was mentioned in other chats: {update}')

    return False
