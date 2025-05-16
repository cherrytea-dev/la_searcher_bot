from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove

from _dependencies.pubsub import save_onboarding_step

from ..buttons import (
    IsMoscow,
    MainMenu,
    MainSettingsMenu,
    OtherOptionsMenu,
    b_back_to_start,
    b_fed_dist_pick_other,
    b_menu_set_region,
    reply_markup_main,
)
from ..common import (
    HandlerResult,
    UpdateBasicParams,
    UpdateExtraParams,
    create_one_column_reply_markup,
)
from ..database import db
from ..decorators import button_handler, callback_handler
from ..message_sending import tg_api
from ..regions import GEO_KEYBOARD_NAME, geography
from .button_handlers import WELCOME_MESSAGE_AFTER_ONBOARDING

USE_NEW_REGION_SELECTION = True  # temporary switch; remove in future
REGION_SELECTION_HELP_TEXT = """Выберите регионы, по которым хотите видеть поиски. Можно фильтровать регионы по первой букве.
Чтобы ОТПИСАТЬСЯ от какого-либо региона – нажмите на его кнопку еще раз."""


@button_handler(buttons=IsMoscow.b_reg_not_moscow.list())
def handle_if_moscow(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    """act if user replied either user from Moscow region or from another one"""

    got_message = update_params.got_message
    user_id = update_params.user_id
    username = update_params.username

    if got_message == IsMoscow.b_reg_moscow:
        save_onboarding_step(user_id, username, 'moscow_replied')
        save_onboarding_step(user_id, username, 'region_set')
        user_role = db().get_user_role(user_id)
        db().save_user_pref_topic_type(user_id, user_role)

        if db().check_if_user_has_no_regions(user_id):
            # add the New User into table user_regional_preferences
            # region is Moscow for Active Searches & InfoPod
            db().add_folder_to_user_regional_preference(user_id, 276)
            db().add_folder_to_user_regional_preference(user_id, 41)
            db().add_region_to_user_settings(user_id, 1)

        return WELCOME_MESSAGE_AFTER_ONBOARDING, reply_markup_main

    if got_message == IsMoscow.b_reg_not_moscow:
        save_onboarding_step(user_id, username, 'moscow_replied')

        if USE_NEW_REGION_SELECTION:
            return _handle_region_selection_inline_menu(update_params)

        bot_message = (
            'Спасибо, тогда для корректной работы Бота, пожалуйста, выберите свой регион: '
            'сначала обозначьте Федеральный Округ, '
            'а затем хотя бы один Регион поисков, чтобы отслеживать поиски в этом регионе. '
            'Вы в любой момент сможете изменить '
            'список регионов через настройки бота.'
        )
        reply_markup = ReplyKeyboardMarkup(geography.keyboard_federal_districts(), resize_keyboard=True)
        return bot_message, reply_markup

    return bot_message, reply_markup_main


@callback_handler(keyboard_name=GEO_KEYBOARD_NAME)
def handle_region_selection_callback(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> HandlerResult:
    assert update_params.got_callback
    selected_button = str(update_params.got_callback.action)
    if selected_button == 'close':
        tg_api().send_callback_answer_to_api(
            update_params.user_id, update_params.callback_query_id, 'Возвращаемся в настройки'
        )

        if extra_params.onboarding_step_id == 20:
            return _handle_onboarding_step_region_is_set(update_params, extra_params)

        return 'Выбор завершен', reply_markup_main  # TODO

    try:
        # user pressed button with region. update value in db and send updated keyboard
        selected_region_index = int(selected_button)
        selected_region_text = geography.get_selected_region_name_by_order(selected_region_index)

        was_updated = _update_list_of_regions(update_params.user_id, selected_region_text)
        if not was_updated:
            flash_message = 'Требуется хотя бы 1 регион'
            tg_api().send_callback_answer_to_api(update_params.user_id, update_params.callback_query_id, flash_message)
            return '', None

        user_curr_regs = db().get_user_regions_from_db(update_params.user_id)
        selected_regions = geography.forum_folders_to_regions_list(user_curr_regs)
        letter_to_show = update_params.got_callback.letter_to_show
        reply_keyboard = geography.get_inline_keyboard_by_first_letter(letter_to_show, selected_regions)

    except ValueError:
        # user pressed button with letter
        user_curr_regs = db().get_user_regions_from_db(update_params.user_id)
        selected_regions = geography.forum_folders_to_regions_list(user_curr_regs)
        reply_keyboard = geography.get_inline_keyboard_by_first_letter(selected_button, selected_regions)

    return (REGION_SELECTION_HELP_TEXT, reply_keyboard)


@button_handler(buttons=[b_menu_set_region, b_fed_dist_pick_other])
def handle_set_region(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    if USE_NEW_REGION_SELECTION:
        return _handle_region_selection_inline_menu(update_params)

    bot_message = _format_user_selected_regions(update_params)

    if update_params.got_message == b_menu_set_region:
        # case for the first entry to the screen of Reg Settings
        pre_msg = (
            'Бот может показывать поиски в любом регионе работы ЛА.\n'
            'Вы можете подписаться на несколько регионов – просто кликните на соответствующие кнопки регионов.'
            '\nЧтобы ОТПИСАТЬСЯ от ненужных регионов – нажмите на соответствующую кнопку региона еще раз.\n\n'
        )
        bot_message = pre_msg + bot_message

    reply_markup = ReplyKeyboardMarkup(geography.keyboard_federal_districts(), resize_keyboard=True)
    return bot_message, reply_markup


def _handle_region_selection_inline_menu(update_params: UpdateBasicParams) -> HandlerResult:
    bot_message = (
        'Бот может показывать поиски в любом регионе работы ЛА.\n' 'Вы можете подписаться на несколько регионов'
    )

    user_curr_regs_list = db().get_user_regions(update_params.user_id)
    selected_regions = geography.forum_folders_to_regions_list(user_curr_regs_list)

    params = {
        'chat_id': update_params.user_id,
        'text': bot_message,
        'reply_markup': ReplyKeyboardRemove(),
    }
    tg_api().send_message(params)

    reply_keyboard = geography.get_inline_keyboard_by_first_letter('+', selected_regions)
    return REGION_SELECTION_HELP_TEXT, reply_keyboard


@button_handler(buttons=geography.federal_district_names())
def handle_message_is_district(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    bot_message = _format_user_selected_regions(update_params)

    reply_markup = ReplyKeyboardMarkup(
        geography.get_keyboard_by_fed_district(update_params.got_message), resize_keyboard=True
    )
    return bot_message, reply_markup


@button_handler(buttons=geography.all_region_names())
def handle_message_is_federal_region(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> HandlerResult:
    user_id = update_params.user_id
    got_message = update_params.got_message

    if extra_params.onboarding_step_id == 20:
        return _handle_onboarding_step_region_is_set(update_params, extra_params)

    updated_regions = _update_and_download_list_of_regions(user_id, got_message)
    keyboard = geography.get_keyboard_by_region(got_message)

    return updated_regions, ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def _handle_onboarding_step_region_is_set(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> HandlerResult:
    # FIXME – 02.12.2023 – un-hiding menu button for the newcomers
    #  (in the future it should be done in manage_user script)

    user_id = update_params.user_id
    username = update_params.username

    user_role = db().get_user_role(user_id)
    tg_api().delete_my_commands(user_id)
    save_onboarding_step(user_id, username, 'region_set')
    db().save_user_pref_topic_type(user_id, user_role)

    keyboard_role = [
        MainSettingsMenu.b_set_pref_notif_type,
        MainSettingsMenu.b_set_pref_coords,
        MainSettingsMenu.b_set_pref_radius,
        MainSettingsMenu.b_set_pref_age,
        MainSettingsMenu.b_set_forum_nick,
        OtherOptionsMenu.b_view_latest_searches,
        MainMenu.b_view_act_searches,
        b_back_to_start,
    ]

    return WELCOME_MESSAGE_AFTER_ONBOARDING, create_one_column_reply_markup(keyboard_role)


def _format_user_selected_regions(update_params: UpdateBasicParams) -> str:
    msg = _get_user_selected_regions_text(update_params.user_id)
    if msg:
        return 'Текущий список ваших регионов:' + msg
    return 'Пока список выбранных регионов пуст. Выберите хотя бы один.'


def _update_list_of_regions(user_id: int, got_message: str) -> bool:
    """
    update the list of user's regions
    return False if user tries to uncheck the last region
    """

    list_of_regs_to_upload = geography.folder_dict()[got_message]
    user_curr_regs = db().get_user_regions_from_db(user_id)

    region_was_in_db = any(list_of_regs_to_upload[0] == user_reg for user_reg in user_curr_regs)
    region_is_the_only = region_was_in_db and len(user_curr_regs) - len(list_of_regs_to_upload) < 1

    if region_is_the_only:
        return False
        # Scenario: this setting WAS in place, but now it's the last one - we cannot delete it

    if region_was_in_db:
        for region in list_of_regs_to_upload:
            db().delete_folder_from_user_regional_preference(user_id, region)
    else:
        for region in list_of_regs_to_upload:
            db().add_folder_to_user_regional_preference(user_id, region)

    return True


def _update_and_download_list_of_regions(user_id: int, got_message: str) -> str:
    """Upload, download and compose a message on the list of user's regions"""

    list_of_regs_to_upload = geography.folder_dict()[got_message]
    user_curr_regs = db().get_user_regions_from_db(user_id)

    region_was_in_db = any(list_of_regs_to_upload[0] == user_reg for user_reg in user_curr_regs)
    region_is_the_only = region_was_in_db and len(user_curr_regs) - len(list_of_regs_to_upload) < 1

    if region_is_the_only:
        # Scenario: this setting WAS in place, but now it's the last one - we cannot delete it
        msg = _get_user_selected_regions_text(user_id)
        msg = (
            'Ваш регион поисков настроен' + msg + '\n\nВы можете продолжить добавлять регионы, либо нажмите '
            'кнопку "в начало", чтобы продолжить работу с ботом.'
        )
        return msg

    # Scenario: this setting WAS in place, and now we need to DELETE it
    if region_was_in_db:
        for region in list_of_regs_to_upload:
            db().delete_folder_from_user_regional_preference(user_id, region)

    # Scenario: it's a NEW setting, we need to ADD it
    else:
        for region in list_of_regs_to_upload:
            db().add_folder_to_user_regional_preference(user_id, region)

    msg = _get_user_selected_regions_text(user_id)
    msg = (
        'Записали. Обновленный список ваших регионов:' + msg + '\n\nВы можете продолжить добавлять регионы, '
        'либо нажмите кнопку "в начало", чтобы '
        'продолжить работу с ботом.'
    )

    return msg


def _get_user_selected_regions_text(user_id: int) -> str:
    user_curr_regs_list = db().get_user_regions(user_id)

    selected_regions = geography.forum_folders_to_regions_list(user_curr_regs_list)
    message_lines: list[str] = []

    message_lines = [' &#8226; ' + user_region for user_region in selected_regions]

    return '\n' + ',\n'.join(message_lines)
