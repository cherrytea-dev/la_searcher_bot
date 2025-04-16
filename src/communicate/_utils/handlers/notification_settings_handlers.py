from enum import Enum

from ..buttons import MainSettingsMenu, NotificationSettingsMenu, b_act_titles, b_back_to_start
from ..common import (
    HandlerResult,
    UpdateBasicParams,
    UpdateExtraParams,
    create_one_column_reply_markup,
)
from ..database import db
from ..decorators import button_handler


class NotificationSettingsMenuOptions(str, Enum):
    new_searches = 'new_searches'
    status_changes = 'status_changes'
    comments_changes = 'comments_changes'
    inforg_comments = 'inforg_comments'
    title_changes = 'title_changes'
    field_trips_new = 'field_trips_new'
    field_trips_change = 'field_trips_change'
    coords_change = 'coords_change'
    first_post_changes = 'first_post_changes'
    all_in_followed_search = 'all_in_followed_search'
    all = 'all'
    bot_news = 'bot_news'  # TODO not used?


def _preference_turn_on(user_id: int, preference: NotificationSettingsMenuOptions) -> None:
    """Save user preference on types of notifications to be sent by bot"""

    # the master-table is dict_notif_types:

    if preference == NotificationSettingsMenuOptions.all:
        db().user_preference_delete(user_id, [])
        db().user_preference_save(user_id, preference)

    elif preference in {
        NotificationSettingsMenuOptions.new_searches,
        NotificationSettingsMenuOptions.status_changes,
        NotificationSettingsMenuOptions.title_changes,
        NotificationSettingsMenuOptions.comments_changes,
        NotificationSettingsMenuOptions.first_post_changes,
        NotificationSettingsMenuOptions.all_in_followed_search,
    }:
        if db().user_preference_is_exists(user_id, [NotificationSettingsMenuOptions.all]):
            db().user_preference_save(user_id, NotificationSettingsMenuOptions.bot_news)
        db().user_preference_delete(user_id, [NotificationSettingsMenuOptions.all])

        db().user_preference_save(user_id, preference)

        if preference == NotificationSettingsMenuOptions.comments_changes:
            db().user_preference_delete(user_id, [NotificationSettingsMenuOptions.inforg_comments])

    elif preference == NotificationSettingsMenuOptions.inforg_comments:
        if not db().user_preference_is_exists(
            user_id, [NotificationSettingsMenuOptions.all, NotificationSettingsMenuOptions.comments_changes]
        ):
            db().user_preference_save(user_id, preference)

    elif preference in {
        NotificationSettingsMenuOptions.field_trips_new,
        NotificationSettingsMenuOptions.field_trips_change,
        NotificationSettingsMenuOptions.coords_change,
    }:
        # FIXME – temp deactivation unlit feature will be ready for prod
        # FIXME – to be added to "new_searches" etc group
        # if not execute_check(user_id, ['all']):
        db().user_preference_save(user_id, preference)


def _preference_turn_off(user_id: int, preference: NotificationSettingsMenuOptions) -> None:
    """Save user preference on types of notifications to be sent by bot"""

    # the master-table is dict_notif_types:

    if preference == NotificationSettingsMenuOptions.all:
        default_preferences = [
            NotificationSettingsMenuOptions.bot_news,
            NotificationSettingsMenuOptions.new_searches,
            NotificationSettingsMenuOptions.status_changes,
            NotificationSettingsMenuOptions.inforg_comments,
            NotificationSettingsMenuOptions.first_post_changes,
        ]
        for pref in default_preferences:
            db().user_preference_save(user_id, pref)

    elif preference == NotificationSettingsMenuOptions.comments_changes:
        db().user_preference_save(user_id, NotificationSettingsMenuOptions.inforg_comments)

    db().user_preference_delete(user_id, [preference])


def _get_notification_settings_keyboard(got_message: str, user_id: int) -> list[str]:
    NPMO = NotificationSettingsMenuOptions  # alias to align following `options_map`` in one line
    NSM = NotificationSettingsMenu
    prefs = db().get_all_user_preferences(user_id)
    if NotificationSettingsMenuOptions.all in prefs:
        return [
            NotificationSettingsMenu.b_deact_all,
            b_back_to_start,
        ]

    keyboard: list[str | NotificationSettingsMenu] = [NSM.b_act_all]
    options_map = (
        (NPMO.new_searches, NSM.b_act_new_search, NSM.b_deact_new_search),
        (NPMO.status_changes, NSM.b_act_stat_change, NSM.b_deact_stat_change),
        (NPMO.comments_changes, NSM.b_act_all_comments, NSM.b_deact_all_comments),
        (NPMO.inforg_comments, NSM.b_act_inforg_com, NSM.b_deact_inforg_com),
        (NPMO.first_post_changes, NSM.b_act_first_post_change, NSM.b_deact_first_post_change),
        (NPMO.all_in_followed_search, NSM.b_act_all_in_followed_search, NSM.b_deact_all_in_followed_search),
    )

    for option, button_if_off, button_if_on in options_map:
        keyboard.append(button_if_on if option in prefs else button_if_off)

    keyboard.append(b_back_to_start)
    return keyboard


def _compose_user_preferences_message(user_id: int) -> tuple[str, list[str]]:
    """Compose a text for user on which types of notifications are enabled for zir"""

    user_prefs = db().get_all_user_preferences(user_id)

    mapping = {
        'all': 'все сообщения',
        'new_searches': ' &#8226; о новых поисках',
        'status_changes': ' &#8226; об изменении статуса',
        'title_changes': ' &#8226; об изменении заголовка',
        'comments_changes': ' &#8226; о всех комментариях',
        'inforg_comments': ' &#8226; о комментариях Инфорга',
        'first_post_changes': ' &#8226; об изменениях в первом посте',
        'all_in_followed_search': ' &#8226; в отслеживаемом поиске - все уведомления',
        'bot_news': '',
    }

    if not user_prefs:
        return 'пока нет включенных уведомлений', user_prefs

    prefs_word_list = [mapping.get(pref, 'неизвестная настройка') for pref in user_prefs]

    return '\n'.join(x for x in prefs_word_list if x), user_prefs


@button_handler(buttons=[MainSettingsMenu.b_set_pref_notif_type])
def handle_notification_settings_show_menu(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> HandlerResult:
    got_message = update_params.got_message
    user_id = update_params.user_id

    prefs = _compose_user_preferences_message(user_id)
    if prefs[0] == 'пока нет включенных уведомлений' or prefs[0] == 'неизвестная настройка':
        bot_message = 'Выберите, какие уведомления вы бы хотели получать'
    else:
        bot_message = 'Сейчас у вас включены следующие виды уведомлений:\n'
        bot_message += prefs[0]

    keyboard_notifications_flexible = _get_notification_settings_keyboard(got_message, user_id)

    reply_markup = create_one_column_reply_markup(keyboard_notifications_flexible)
    return bot_message, reply_markup


@button_handler(buttons=[b_act_titles, *NotificationSettingsMenu.list()])
def handle_notification_settings(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    got_message = update_params.got_message
    user_id = update_params.user_id

    if got_message == NotificationSettingsMenu.b_act_all:
        bot_message = (
            'Супер! теперь вы будете получать уведомления в телеграм в случаях: '
            'появление нового поиска, изменение статуса поиска (стоп, НЖ, НП), '
            'появление новых комментариев по всем поискам. Вы в любой момент '
            'можете изменить список уведомлений'
        )
        _preference_turn_on(user_id, NotificationSettingsMenuOptions.all)

    elif got_message == NotificationSettingsMenu.b_deact_all:
        bot_message = 'Вы можете настроить типы получаемых уведомлений более гибко'
        _preference_turn_off(user_id, NotificationSettingsMenuOptions.all)

    elif got_message == NotificationSettingsMenu.b_act_new_search:
        bot_message = (
            'Отлично! Теперь вы будете получать уведомления в телеграм при '
            'появлении нового поиска. Вы в любой момент можете изменить '
            'список уведомлений'
        )
        _preference_turn_on(user_id, NotificationSettingsMenuOptions.new_searches)

    elif got_message == NotificationSettingsMenu.b_deact_new_search:
        bot_message = 'Записали'
        _preference_turn_off(user_id, NotificationSettingsMenuOptions.new_searches)

    elif got_message == NotificationSettingsMenu.b_act_stat_change:
        bot_message = (
            'Отлично! теперь вы будете получать уведомления в телеграм при '
            'изменении статуса поисков (НЖ, НП, СТОП и т.п.). Вы в любой момент '
            'можете изменить список уведомлений'
        )
        _preference_turn_on(user_id, NotificationSettingsMenuOptions.status_changes)

    elif got_message == NotificationSettingsMenu.b_deact_stat_change:
        bot_message = 'Записали'
        _preference_turn_off(user_id, NotificationSettingsMenuOptions.status_changes)

    elif got_message == b_act_titles:
        bot_message = 'Отлично!'
        _preference_turn_on(user_id, NotificationSettingsMenuOptions.title_changes)

    elif got_message == NotificationSettingsMenu.b_act_all_comments:
        bot_message = (
            'Отлично! Теперь все новые комментарии будут у вас! Вы в любой момент ' 'можете изменить список уведомлений'
        )
        _preference_turn_on(user_id, NotificationSettingsMenuOptions.comments_changes)

    elif got_message == NotificationSettingsMenu.b_deact_all_comments:
        bot_message = (
            'Записали. Мы только оставили вам включенными уведомления о '
            'комментариях Инфорга. Их тоже можно отключить'
        )
        _preference_turn_off(user_id, NotificationSettingsMenuOptions.comments_changes)

    elif got_message == NotificationSettingsMenu.b_act_inforg_com:
        bot_message = (
            'Если вы не подписаны на уведомления по всем комментариям, то теперь '
            'вы будете получать уведомления о комментариях от Инфорга. Если же вы '
            'уже подписаны на все комментарии – то всё остаётся без изменений: бот '
            'уведомит вас по всем комментариям, включая от Инфорга'
        )
        _preference_turn_on(user_id, NotificationSettingsMenuOptions.inforg_comments)

    elif got_message == NotificationSettingsMenu.b_deact_inforg_com:
        bot_message = 'Вы отписались от уведомлений по новым комментариям от Инфорга'
        _preference_turn_off(user_id, NotificationSettingsMenuOptions.inforg_comments)

    elif got_message == NotificationSettingsMenu.b_act_field_trips_new:
        bot_message = (
            'Теперь вы будете получать уведомления о новых выездах по уже идущим '
            'поискам. Обратите внимание, что это не рассылка по новым темам на '
            'форуме, а именно о том, что в существующей теме в ПЕРВОМ посте '
            'появилась информация о новом выезде'
        )
        _preference_turn_on(user_id, NotificationSettingsMenuOptions.field_trips_new)

    elif got_message == NotificationSettingsMenu.b_deact_field_trips_new:
        bot_message = 'Вы отписались от уведомлений по новым выездам'
        _preference_turn_off(user_id, NotificationSettingsMenuOptions.field_trips_new)

    elif got_message == NotificationSettingsMenu.b_act_field_trips_change:
        bot_message = (
            'Теперь вы будете получать уведомления о ключевых изменениях при '
            'выездах, в т.ч. изменение или завершение выезда. Обратите внимание, '
            'что эта рассылка отражает изменения только в ПЕРВОМ посте поиска.'
        )
        _preference_turn_on(user_id, NotificationSettingsMenuOptions.field_trips_change)

    elif got_message == NotificationSettingsMenu.b_deact_field_trips_change:
        bot_message = 'Вы отписались от уведомлений по изменениям выездов'
        _preference_turn_off(user_id, NotificationSettingsMenuOptions.field_trips_change)

    elif got_message == NotificationSettingsMenu.b_act_coords_change:
        bot_message = (
            'Если у штаба поменяются координаты (и об этом будет написано в первом '
            'посте на форуме) – бот уведомит вас об этом'
        )
        _preference_turn_on(user_id, NotificationSettingsMenuOptions.coords_change)

    elif got_message == NotificationSettingsMenu.b_deact_coords_change:
        bot_message = 'Вы отписались от уведомлений о смене места (координат) штаба'
        _preference_turn_off(user_id, NotificationSettingsMenuOptions.coords_change)

    elif got_message == NotificationSettingsMenu.b_act_first_post_change:
        bot_message = (
            'Теперь вы будете получать уведомления о важных изменениях в Первом Посте'
            ' Инфорга, где обозначено описание каждого поиска'
        )
        _preference_turn_on(user_id, NotificationSettingsMenuOptions.first_post_changes)

    elif got_message == NotificationSettingsMenu.b_deact_first_post_change:
        bot_message = (
            'Вы отписались от уведомлений о важных изменениях в Первом Посте Инфорга c описанием каждого поиска'
        )
        _preference_turn_off(user_id, NotificationSettingsMenuOptions.first_post_changes)

    elif got_message == NotificationSettingsMenu.b_act_all_in_followed_search:
        bot_message = 'Теперь во время отслеживания поиска будут все уведомления по нему.'
        _preference_turn_on(user_id, NotificationSettingsMenuOptions.all_in_followed_search)

    elif got_message == NotificationSettingsMenu.b_deact_all_in_followed_search:
        bot_message = 'Теперь по отслеживаемым поискам будут уведомления как обычно (только настроенные).'
        _preference_turn_off(user_id, NotificationSettingsMenuOptions.all_in_followed_search)

    else:
        bot_message = 'empty message'

    keyboard_notifications_flexible = _get_notification_settings_keyboard(got_message, user_id)

    reply_markup = create_one_column_reply_markup(keyboard_notifications_flexible)
    return bot_message, reply_markup
