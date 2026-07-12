from telegram import ReplyKeyboardRemove

from _dependencies.bot.users_management import save_onboarding_step
from _dependencies.common.telegram_message import TelegramMessage

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
    create_one_column_reply_markup,
)
from ..decorators import tg_handle
from ..handler_context import TGHandlerContext
from ..regions import GEO_KEYBOARD_NAME, geography
from .button_handlers import WELCOME_MESSAGE_AFTER_ONBOARDING

REGION_SELECTION_HELP_TEXT = """Выберите регионы, по которым хотите видеть поиски. Можно фильтровать регионы по первой букве.
Чтобы ОТПИСАТЬСЯ от какого-либо региона – нажмите на его кнопку еще раз."""


@tg_handle(text=IsMoscow.b_reg_not_moscow.list())
def handle_if_moscow(ctx: TGHandlerContext) -> None:
    """act if user replied either user from Moscow region or from another one"""

    got_message = ctx.update_params.got_message
    user_id = ctx.user_id

    if got_message == IsMoscow.b_reg_moscow:
        save_onboarding_step(user_id, 'moscow_replied')
        save_onboarding_step(user_id, 'region_set')
        user_role = ctx.db.get_user_role(user_id)
        ctx.db.save_user_pref_topic_type(user_id, user_role)

        if ctx.db.check_if_user_has_no_regions(user_id):
            # add the New User into table user_regional_preferences
            # region is Moscow for Active Searches & InfoPod
            ctx.db.add_folder_to_user_regional_preference(user_id, 276)
            ctx.db.add_folder_to_user_regional_preference(user_id, 41)
            ctx.db.add_user_region_setting(user_id, 1)

        ctx.reply(WELCOME_MESSAGE_AFTER_ONBOARDING, reply_markup=reply_markup_main)
        return

    if got_message == IsMoscow.b_reg_not_moscow:
        save_onboarding_step(user_id, 'moscow_replied')
        _handle_region_selection_inline_menu(ctx)
        return

    ctx.reply('', reply_markup=reply_markup_main)


@tg_handle(callback_keyboard=GEO_KEYBOARD_NAME)
def handle_region_selection_callback(ctx: TGHandlerContext) -> None:
    assert ctx.update_params.got_callback
    selected_button = str(ctx.update_params.got_callback.action)
    if selected_button == 'close':
        ctx.answer_callback('Возвращаемся в настройки')

        if ctx.extra_params.onboarding_step_id == 20:
            _handle_onboarding_step_region_is_set(ctx)
            return

        ctx.reply('Выбор завершен', reply_markup=reply_markup_main)
        return

    try:
        # user pressed button with region. update value in db and send updated keyboard
        selected_region_index = int(selected_button)
        selected_region_text = geography.get_selected_region_name_by_order(selected_region_index)

        was_updated = _update_list_of_regions(ctx, ctx.user_id, selected_region_text)
        if not was_updated:
            flash_message = 'Требуется хотя бы 1 регион'
            ctx.answer_callback(flash_message)
            return

        user_curr_regs = ctx.db.get_user_regions_from_db(ctx.user_id)
        selected_regions = geography.forum_folders_to_regions_list(user_curr_regs)
        letter_to_show = ctx.update_params.got_callback.letter_to_show
        reply_keyboard = geography.get_inline_keyboard_by_first_letter(letter_to_show, selected_regions)

    except ValueError:
        # user pressed button with letter
        user_curr_regs = ctx.db.get_user_regions_from_db(ctx.user_id)
        selected_regions = geography.forum_folders_to_regions_list(user_curr_regs)
        reply_keyboard = geography.get_inline_keyboard_by_first_letter(selected_button, selected_regions)

    ctx.edit(REGION_SELECTION_HELP_TEXT, reply_markup=reply_keyboard)


@tg_handle(text=[b_menu_set_region, b_fed_dist_pick_other])
def handle_set_region(ctx: TGHandlerContext) -> None:
    _handle_region_selection_inline_menu(ctx)


def _handle_region_selection_inline_menu(ctx: TGHandlerContext) -> None:
    bot_message = (
        'Бот может показывать поиски в любом регионе работы ЛА.\n' 'Вы можете подписаться на несколько регионов'
    )

    user_curr_regs_list = ctx.db.get_user_regions(ctx.user_id)
    selected_regions = geography.forum_folders_to_regions_list(user_curr_regs_list)

    ctx.tg_api.send_message(
        ctx.user_id,
        TelegramMessage(
            text=bot_message,
            reply_markup=ReplyKeyboardRemove(),
        ),
    )

    reply_keyboard = geography.get_inline_keyboard_by_first_letter('+', selected_regions)
    ctx.reply(REGION_SELECTION_HELP_TEXT, reply_markup=reply_keyboard)


def _handle_onboarding_step_region_is_set(ctx: TGHandlerContext) -> None:
    # FIXME – 02.12.2023 – un-hiding menu button for the newcomers
    #  (in the future it should be done in manage_user script)

    user_id = ctx.user_id

    user_role = ctx.db.get_user_role(user_id)
    ctx.tg_api.delete_my_commands(user_id)
    save_onboarding_step(user_id, 'region_set')
    ctx.db.save_user_pref_topic_type(user_id, user_role)

    keyboard_role = [
        MainSettingsMenu.b_set_pref_notif_type,
        MainSettingsMenu.b_set_pref_coords,
        MainSettingsMenu.b_set_pref_radius,
        MainSettingsMenu.b_set_pref_age,
        MainSettingsMenu.b_set_forum_nick,
        MainSettingsMenu.b_set_vkontakte_nick,
        OtherOptionsMenu.b_view_latest_searches,
        MainMenu.b_view_act_searches,
        b_back_to_start,
    ]

    ctx.reply(WELCOME_MESSAGE_AFTER_ONBOARDING, reply_markup=create_one_column_reply_markup(keyboard_role))


def _update_list_of_regions(ctx: TGHandlerContext, user_id: int, got_message: str) -> bool:
    """
    update the list of user's regions
    return False if user tries to uncheck the last region
    """

    list_of_regs_to_upload = geography.folder_dict()[got_message]
    user_curr_regs = ctx.db.get_user_regions_from_db(user_id)

    region_was_in_db = any(list_of_regs_to_upload[0] == user_reg for user_reg in user_curr_regs)
    region_is_the_only = region_was_in_db and len(user_curr_regs) - len(list_of_regs_to_upload) < 1

    if region_is_the_only:
        return False
        # Scenario: this setting WAS in place, but now it's the last one - we cannot delete it

    if region_was_in_db:
        for region in list_of_regs_to_upload:
            ctx.db.delete_folder_from_user_regional_preference(user_id, region)
    else:
        for region in list_of_regs_to_upload:
            ctx.db.add_folder_to_user_regional_preference(user_id, region)

    return True
