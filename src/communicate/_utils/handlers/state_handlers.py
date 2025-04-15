import logging
import re

from telegram import ReplyKeyboardMarkup

from _dependencies.commons import Topics, publish_to_pubsub
from communicate._utils.buttons import (
    CoordinateSettingsMenu,
    DistanceSettings,
    MainSettingsMenu,
    b_admin_menu,
    b_back_to_start,
    b_coords_auto_def,
    b_test_menu,
    reply_markup_main,
)
from communicate._utils.common import (
    HandlerResult,
    UpdateBasicParams,
    UpdateExtraParams,
    UserInputState,
    create_one_column_reply_markup,
    generate_yandex_maps_place_link,
)
from communicate._utils.database import db
from communicate._utils.decorators import state_handler


@state_handler(UserInputState.radius_input)
def handle_radius_value(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    number = _parse_radius(update_params.got_message)

    if not number:
        bot_message = 'Не могу разобрать цифры. Давайте еще раз попробуем?'
        list_of_buttons_1 = [
            DistanceSettings.b_pref_radius_act,
            MainSettingsMenu.b_set_pref_radius,
            b_back_to_start,
        ]
        reply_markup = create_one_column_reply_markup(list_of_buttons_1)
        return bot_message, reply_markup

    db().save_user_radius(update_params.user_id, number)
    saved_radius = db().check_saved_radius(update_params.user_id)
    bot_message = (
        f'Сохранили! Теперь поиски, у которых расстояние до штаба, '
        f'либо до ближайшего населенного пункта (топонима) превосходит '
        f'{saved_radius} км по прямой, не будут вас больше беспокоить. '
        f'Настройку можно изменить в любое время.'
    )
    list_of_buttons = (
        DistanceSettings.b_pref_radius_change,
        DistanceSettings.b_pref_radius_deact,
        MainSettingsMenu.b_set_pref_radius,
        b_back_to_start,
    )

    reply_markup = create_one_column_reply_markup(list_of_buttons)

    return bot_message, reply_markup


def _parse_radius(got_message: str) -> int | None:
    match = re.search(r'[0-9]{1,6}', str(got_message))
    if match:
        return int(match.group())
    return None


@state_handler(UserInputState.input_of_forum_username)
def handle_linking_to_forum_user_input(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> HandlerResult:
    """manage all interactions regarding connection of telegram and forum user accounts"""

    got_message = update_params.got_message
    if got_message in {b_admin_menu, b_back_to_start, b_test_menu} or len(got_message.split()) < 4:
        return 'Неправильный логин, попробуйте еще раз', reply_markup_main

    message_for_pubsub = [update_params.user_id, got_message]
    publish_to_pubsub(Topics.parse_user_profile_from_forum, message_for_pubsub)
    bot_message = 'Сейчас посмотрю, это может занять до 10 секунд...'
    keyboard = [b_back_to_start]
    reply_markup = create_one_column_reply_markup(keyboard)
    return bot_message, reply_markup


@state_handler(UserInputState.input_of_coords_man)
def handle_user_coordinates_from_text(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> HandlerResult:
    """process coordinates which user sent to bot"""
    user_latitude, user_longitude = _get_coordinates_from_string(update_params.got_message)
    if not user_latitude or not user_longitude:
        keyboard_coordinates_1 = (
            b_coords_auto_def,
            CoordinateSettingsMenu.b_coords_man_def,
            CoordinateSettingsMenu.b_coords_check,
            CoordinateSettingsMenu.b_coords_del,
            b_back_to_start,
        )
        reply_markup = create_one_column_reply_markup(keyboard_coordinates_1)

        return 'Координаты не распознаны.', reply_markup

    db().save_user_coordinates(update_params.user_id, user_latitude, user_longitude)

    bot_message = 'Ваши "домашние координаты" сохранены:\n'
    bot_message += generate_yandex_maps_place_link(user_latitude, user_longitude, 'coords')
    bot_message += (
        '\nТеперь для всех поисков, где удастся распознать координаты штаба или '
        'населенного пункта, будет указываться направление и расстояние по '
        'прямой от ваших "домашних координат".'
    )
    keyboard_settings = (
        CoordinateSettingsMenu.b_coords_check,
        CoordinateSettingsMenu.b_coords_del,
        b_back_to_start,
    )
    reply_markup = create_one_column_reply_markup(keyboard_settings)

    return bot_message, reply_markup


def _get_coordinates_from_string(got_message: str) -> tuple[float, float] | tuple[None, None]:
    """gets coordinates from string"""

    # Check if user input is in format of coordinates
    # noinspection PyBroadException
    try:
        numbers = [float(s) for s in re.findall(r'-?\d+\.?\d*', got_message)]
        if numbers and len(numbers) > 1 and 30 < numbers[0] < 80 and 10 < numbers[1] < 190:
            return numbers[0], numbers[1]
    except Exception:
        logging.info(f'manual coordinates were not identified from string {got_message}')

    return None, None
