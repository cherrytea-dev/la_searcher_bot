import logging
import re

from telegram import (
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)

from _dependencies.bot.users_management import ManageUserAction
from _dependencies.models import AgePeriod

from ..buttons import (
    Commands,
    MainMenu,
    MainSettingsMenu,
    ResetSettingsConfirm,
    TopicTypeInlineKeyboardBuilder,
    b_back_to_start,
    b_menu_set_region,
)
from ..common import (
    create_one_column_reply_markup,
)
from ..decorators import tg_handle
from ..handler_context import TGHandlerContext


def _get_default_age_period_list() -> list[AgePeriod]:
    return [
        AgePeriod(description='Маленькие Дети 0-6 лет', name='0-6', min_age=0, max_age=6, order=0),
        AgePeriod(description='Подростки 7-13 лет', name='7-13', min_age=7, max_age=13, order=1),
        AgePeriod(description='Молодежь 14-20 лет', name='14-20', min_age=14, max_age=20, order=2),
        AgePeriod(description='Взрослые 21-50 лет', name='21-50', min_age=21, max_age=50, order=3),
        AgePeriod(description='Старшее Поколение 51-80 лет', name='51-80', min_age=51, max_age=80, order=4),
        AgePeriod(description='Старцы более 80 лет', name='80-on', min_age=80, max_age=120, order=5),
    ]


def _manage_age(ctx: TGHandlerContext, user_id: int, got_message: str | None) -> tuple[list[list[str]], bool]:
    """Save user Age preference and generate the list of updated Are preferences"""

    if got_message:
        user_want_activate = bool(re.search(r'(?i)включить', got_message))
        user_new_setting = re.sub(r'.*чить: ', '', got_message)

        for line in _get_default_age_period_list():
            if user_new_setting == line.description:
                if user_want_activate:
                    ctx.db.save_user_age_prefs(user_id, line)
                else:
                    ctx.db.delete_user_age_pref(user_id, line)
                break

    return _get_user_age_prefs_params(ctx, user_id)


def _get_user_age_prefs_params(ctx: TGHandlerContext, user_id: int) -> tuple[list[list[str]], bool]:
    # Block for Generating a list of Buttons
    age_list = _get_default_age_period_list()

    raw_list_of_periods = ctx.db.get_age_prefs(user_id)
    first_visit = False

    if raw_list_of_periods and str(raw_list_of_periods) != 'None':
        for line_raw in raw_list_of_periods:
            got_min, got_max = int(list(line_raw)[0]), int(list(line_raw)[1])
            for line_a in age_list:
                if int(line_a.min_age) == got_min and int(line_a.max_age) == got_max:
                    line_a.active = True
    else:
        first_visit = True
        for line in age_list:
            line.active = True
            ctx.db.save_user_age_prefs(user_id, line)

    list_of_buttons = []

    for line in age_list:
        button_text = f'отключить: {line.description}' if line.active else f'включить: {line.description}'
        list_of_buttons.append([button_text])

    return list_of_buttons, first_visit


def _get_age_buttons() -> list[str]:
    age_buttons = []
    for period in _get_default_age_period_list():
        age_buttons.append(f'отключить: {period.description}')
        age_buttons.append(f'включить: {period.description}')
    return age_buttons


@tg_handle(text=[MainSettingsMenu.b_set_pref_age, *_get_age_buttons()])
def handle_age_settings(ctx: TGHandlerContext) -> None:
    got_message = ctx.update_params.got_message
    input_data = None if got_message == MainSettingsMenu.b_set_pref_age else got_message
    keyboard, first_visit = _manage_age(ctx, ctx.user_id, input_data)
    keyboard.append([b_back_to_start])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if got_message == MainSettingsMenu.b_set_pref_age:
        # TODO never True
        bot_message = (
            'Чтобы включить или отключить уведомления по определенной возрастной '
            'группе, нажмите на неё. Настройку можно изменить в любой момент.'
        )
        if first_visit:
            bot_message = (
                'Данное меню позволяет выбрать возрастные категории БВП '
                '(без вести пропавших), по которым вы хотели бы получать уведомления. '
                'Важно, что если бот не сможет распознать возраст БВП, тогда вы '
                'всё равно получите уведомление.\nТакже данная настройка не влияет на '
                'разделы Актуальные Поиски и Последние Поиски – в них вы всё также '
                'сможете увидеть полный список поисков.\n\n' + bot_message
            )
    else:
        bot_message = 'Спасибо, записали.'
    ctx.reply(text=bot_message, reply_markup=reply_markup)


def _compose_msg_on_user_setting_fullness(ctx: TGHandlerContext, user_id: int) -> str | None:
    """Create a text of message, which describes the degree on how complete user's profile is.
    More settings set – more complete profile it. It's done to motivate users to set the most tailored settings."""

    if not user_id:
        return None

    settings_summary = ctx.db.get_user_settings_summary(user_id)

    if not settings_summary:
        return None

    list_of_settings = [
        settings_summary.pref_notif_type,
        settings_summary.pref_region_old,
        settings_summary.pref_coords,
        settings_summary.pref_radius,
        settings_summary.pref_age,
        settings_summary.pref_forum,
    ]
    user_score = int(round(sum(list_of_settings) / len(list_of_settings) * 100, 0))

    logging.info(f'List of user settings activation: {list_of_settings=}')
    logging.info(f'User settings completeness score is {user_score}')

    if user_score == 100:
        return None

    user_score_emoji = (
        f'{user_score // 10}\U0000fe0f\U000020e3{user_score - (user_score // 10) * 10}\U0000fe0f\U000020e3'
    )
    message_parts = [
        f'Вы настроили бот на {user_score_emoji}%.',
        '',
        'Чтобы сделать бот максимально эффективным именно для вас, рекомендуем настроить следующие параметры:',
    ]
    if not settings_summary.pref_notif_type:
        message_parts.append(' - Тип уведомлений,')
    if not settings_summary.pref_region_old:
        message_parts.append(' - Регион,')
    if not settings_summary.pref_coords:
        message_parts.append(' - Домашние координаты,')
    if not settings_summary.pref_radius:
        message_parts.append(' - Максимальный радиус,')
    if not settings_summary.pref_age:
        message_parts.append(' - Возрастные группы БВП,')
    if not settings_summary.pref_forum:
        message_parts.append(' - Связать бот с форумом ЛА,')

    return '\n'.join(message_parts)


@tg_handle(text=[MainMenu.b_settings, Commands.c_settings])
def handle_main_settings(ctx: TGHandlerContext) -> None:
    bot_message = (
        'Это раздел с настройками. Здесь вы можете выбрать удобные для вас '
        'уведомления, а также ввести свои "домашние координаты", на основе которых '
        'будет рассчитываться расстояние и направление до места поиска. Вы в любой '
        'момент сможете изменить эти настройки.'
    )

    message_prefix = _compose_msg_on_user_setting_fullness(ctx, ctx.user_id)
    if message_prefix:
        bot_message = f'{bot_message}\n\n{message_prefix}'

    delivery_status_button = (
        MainSettingsMenu.b_enable_notifications
        if ctx.db.get_user_status(ctx.user_id) == 'unsubscribed'
        else MainSettingsMenu.b_disable_notifications
    )
    keyboard = [
        delivery_status_button,
        MainSettingsMenu.b_set_pref_notif_type,
        b_menu_set_region,
        MainSettingsMenu.b_set_topic_type,
        MainSettingsMenu.b_set_pref_coords,
        MainSettingsMenu.b_set_pref_radius,
        MainSettingsMenu.b_set_pref_age,
        MainSettingsMenu.b_set_forum_nick,
        MainSettingsMenu.b_reset_settings,
        b_back_to_start,
    ]  # #AK added b_set_forum_nick for issue #6
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))


@tg_handle(text=MainSettingsMenu.b_disable_notifications)
def handle_disable_notifications(ctx: TGHandlerContext) -> None:
    """Explicitly unsubscribe a user from all notification composing."""
    ctx.db.update_user_status(ctx.user_id, ManageUserAction.unsubscribe_user)
    bot_message = (
        'Уведомления полностью отключены. Бот больше не будет готовить для вас '
        'новые уведомления о поисках.\n\n'
        'Если захотите вернуться, нажмите «включить уведомления».'
    )
    keyboard = [MainSettingsMenu.b_enable_notifications, b_back_to_start]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))


@tg_handle(text=MainSettingsMenu.b_enable_notifications)
def handle_enable_notifications(ctx: TGHandlerContext) -> None:
    """Re-enable notification composing for a user."""
    ctx.db.update_user_status(ctx.user_id, ManageUserAction.subscribe_user)
    bot_message = (
        'Уведомления снова включены. Бот будет присылать сообщения согласно '
        'вашим сохранённым настройкам регионов и типов уведомлений.'
    )
    keyboard = [MainSettingsMenu.b_set_pref_notif_type, b_menu_set_region, b_back_to_start]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))


@tg_handle(text=MainSettingsMenu.b_reset_settings)
def handle_reset_settings_confirm_prompt(ctx: TGHandlerContext) -> None:
    """Show confirmation before resetting settings to defaults."""
    bot_message = (
        'Точно сбросить настройки?\n\n'
        'Будут удалены: регионы, домашние координаты, радиус, возрастные группы, '
        'отслеживание поисков. Уведомления и виды поисков вернутся к стандартным.\n\n'
        'Роль и привязка аккаунтов не изменятся.'
    )
    keyboard = [ResetSettingsConfirm.b_reset_confirm, ResetSettingsConfirm.b_reset_cancel]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))


@tg_handle(text=ResetSettingsConfirm.b_reset_confirm)
def handle_reset_settings_confirm(ctx: TGHandlerContext) -> None:
    """Reset settings to defaults, then prompt region re-selection."""
    ctx.db.reset_user_settings(ctx.user_id)
    bot_message = (
        'Готово, все настройки сброшены.\n\nРегион теперь не выбран — настройте его заново, чтобы получать уведомления.'
    )
    keyboard = [b_menu_set_region, b_back_to_start]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))


@tg_handle(text=ResetSettingsConfirm.b_reset_cancel)
def handle_reset_settings_cancel(ctx: TGHandlerContext) -> None:
    """Cancel the reset — keep settings as-is."""
    bot_message = 'Ок, ничего не трогаю. Ваши настройки не изменились.'
    keyboard = [MainSettingsMenu.b_set_pref_notif_type, b_menu_set_region, b_back_to_start]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))


@tg_handle(text=MainSettingsMenu.b_set_topic_type)
def handle_topic_type_show_menu(ctx: TGHandlerContext) -> None:
    """Save user Topic Type preference and generate the actual topic type preference message"""

    # when user just enters the MENU for topic types
    bot_message = (
        'Вы можете выбрать и в любой момент поменять, по каким типам поисков или '
        'мероприятий бот должен присылать уведомления.'
    )

    list_of_current_setting_ids = ctx.db.check_saved_topic_types(ctx.user_id)

    keyboard = TopicTypeInlineKeyboardBuilder.get_keyboard(list_of_current_setting_ids, [])
    reply_markup = InlineKeyboardMarkup(keyboard)

    ctx.reply(text=bot_message, reply_markup=reply_markup)
