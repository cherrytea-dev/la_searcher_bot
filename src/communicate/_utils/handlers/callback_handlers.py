import logging
from ast import literal_eval

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from _dependencies.commons import SearchFollowingMode

from ..buttons import TopicTypeInlineKeyboardBuilder, reply_markup_main
from ..common import (
    NOT_FOLLOWING_MARK,
    HandlerResult,
    UpdateBasicParams,
    UpdateExtraParams,
)
from ..database import db
from ..decorators import callback_handler
from ..message_sending import tg_api


@callback_handler(keyboard_name=TopicTypeInlineKeyboardBuilder.keyboard_code)
def handle_topic_type_user_changed(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> tuple[str, InlineKeyboardMarkup]:
    """Save user Topic Type preference and generate the actual topic type preference message"""

    user_callback = update_params.got_callback
    callback_id = update_params.callback_query_id
    user_id = update_params.user_id

    welcome_message = (
        'Вы можете выбрать и в любой момент поменять, по каким типам поисков или '
        'мероприятий бот должен присылать уведомления.'
    )
    bot_message = welcome_message

    if user_callback and user_callback['action'] == 'about':
        # when user push "ABOUT" button
        return _handle_topic_type_pressed_about(update_params, welcome_message)

    # when user pushed INLINE BUTTON for topic type
    list_of_ids_to_change_now = []
    list_of_current_setting_ids = db().check_saved_topic_types(user_id)
    topic_id = TopicTypeInlineKeyboardBuilder.get_topic_id_by_button(user_callback)
    assert topic_id is not None  # would be None only if "about" pushed

    list_of_ids_to_change_now = [topic_id]
    user_wants_to_enable = TopicTypeInlineKeyboardBuilder.if_user_enables(user_callback)
    if user_wants_to_enable is None:
        flash_message = ''
        pass
    elif user_wants_to_enable is True:  # not a poor design – function can be: None, True, False   # noqa
        flash_message = 'Супер, мы включили эти уведомления'
        tg_api().send_callback_answer_to_api(update_params.user_id, callback_id, flash_message)
        db().record_topic_type(user_id, topic_id)
    else:  # user_wants_to_enable == False:  # not a poor design – function can be: None, True, False # noqa
        if len(list_of_current_setting_ids) == 1:
            flash_message = '❌ Необходима как минимум одна настройка'
            list_of_ids_to_change_now = []
            tg_api().send_callback_answer_to_api(update_params.user_id, callback_id, flash_message)
        else:
            flash_message = 'Хорошо, мы изменили список настроек'
            tg_api().send_callback_answer_to_api(update_params.user_id, callback_id, flash_message)
            db().delete_user_saved_topic_type(user_id, topic_id)

    keyboard = TopicTypeInlineKeyboardBuilder.get_keyboard(list_of_current_setting_ids, list_of_ids_to_change_now)
    reply_markup = InlineKeyboardMarkup(keyboard)

    return bot_message, reply_markup


def _handle_topic_type_pressed_about(
    update_params: UpdateBasicParams, welcome_message: str
) -> tuple[str, InlineKeyboardMarkup]:
    """This scenario assumes three steps:
    1. send the "ABOUT" message,
    2. delete prev MENU message
    3. send NEW MENU"""

    callback_query = update_params.callback_query
    user_id = update_params.user_id

    about_text = (
        'ЛизаАлерт проводит несколько типов поисковых мероприятий. В Боте доступны следующие из '
        'них:\n\n'
        '• <b>Стандартные активные поиски</b> – это самые частые поиски: потерялся человек, нужно его '
        'найти, чаще всего на местности. 90% всех поисков попадают в эту категорию.\n'
        '• <b>Резонансные поиски</b> (или "Резонансы") – это срочные поиски федерального масштаба. '
        'На такие поиски призываются поисковики из разных регионов.\n'
        '• <b>Информационная поддержка</b> – это поиски, когда не требуется выезд на поисковые '
        'мероприятия, а лишь требуют помощи в распространении информации о пропавшем в в соц сетях.\n'
        '• <b>Обратные поиски</b> (поиски родных) – бывает, что находят людей, которые не могут '
        'сообщить, кто они, где они живут (потеря памяти). В таких случаях требуется поиск '
        'родственников.\n'
        '• <b>Учебные поиски</b> – это важные поиски, которые созданы ЛизаАлерт, максимально приближены'
        'по условиям к реальным поискам на местности и призваны отрабатывать навыки поиска и спасения'
        'людей в реальных условиях. Создатели бота очень рекомендуют участвовать в '
        'Учебных поисках, чтобы повышать свои навыки как поисковика.\n'
        '• <b>Ночной патруль</b> – в некоторых регионах проводятся ночные патрули в парках и других '
        'общественных зонах.\n'
        '• <b>Мероприятия</b> – это различные встречи, проводимые отрядами ЛизаАлерт. Тематика и '
        'календарь проведения сильно варьируются от региона к региону. Рекомендуем подписаться, '
        'чтобы быть в курсе всех событий в отряде вашего региона. 💡'
    )
    about_params = {'chat_id': user_id, 'text': about_text, 'parse_mode': 'HTML'}
    tg_api().send_message(about_params, "main() if ... user_callback['action'] == 'about'")
    del_message_id = callback_query.message.message_id if callback_query and callback_query.message else None
    if del_message_id:  ###was get_last_user_inline_dialogue( user_id)
        tg_api().delete_message(user_id, del_message_id)
        bot_message = f'⬆️ Справка приведена выше. \n\n{welcome_message}'

    list_of_current_setting_ids = db().check_saved_topic_types(user_id)
    keyboard = TopicTypeInlineKeyboardBuilder.get_keyboard(list_of_current_setting_ids, [])
    return bot_message, InlineKeyboardMarkup(keyboard)


@callback_handler(actions=['search_follow_mode_on', 'search_follow_mode_off'])
def handle_search_follow_mode(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    """Switches search following mode on/off"""

    user_callback = update_params.got_callback
    callback_query = update_params.callback_query
    callback_id = update_params.callback_query_id
    user_id = update_params.user_id

    logging.info(f'{callback_query=}, {user_id=}')
    # when user pushed INLINE BUTTON for topic following
    if user_callback and user_callback['action'] == 'search_follow_mode_on':
        db().set_search_follow_mode(user_id, True)
        bot_message = 'Режим выбора поисков для отслеживания включен.'

    elif user_callback and user_callback['action'] == 'search_follow_mode_off':
        db().set_search_follow_mode(user_id, False)
        bot_message = 'Режим выбора поисков для отслеживания отключен.'

    tg_api().send_callback_answer_to_api(update_params.user_id, callback_id, bot_message)

    return bot_message, reply_markup_main


@callback_handler(actions=['search_follow_mode'])
def manage_search_whiteness(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> tuple[str, InlineKeyboardMarkup]:
    """Saves search_whiteness (accordingly to user's choice of search to follow) and regenerates the search list keyboard"""
    user_callback = update_params.got_callback
    callback_query = update_params.callback_query

    bot_message = ''

    # issue#425 inspired by manage_topic_type
    ################# ToDo further: modify select in compose_notifications

    # when user pushed INLINE BUTTON for topic following
    if not user_callback or user_callback['action'] != 'search_follow_mode':
        return 'Не удалось обработать смену пометки', InlineKeyboardMarkup([])

    # get inline keyboard from previous message to update it
    source_reply_markup = callback_query.message.reply_markup  # type:ignore [union-attr]
    source_keyboard = source_reply_markup.inline_keyboard  # type:ignore [union-attr]

    search_num = int(user_callback['hash'])
    pushed_row_index = _get_pressed_button_row_index(source_reply_markup, search_num)  # type:ignore [union-attr, arg-type]
    if pushed_row_index is None:
        logging.error(f'cannot find pressed button. {search_num=} {source_keyboard=}')
        return 'Не удалось обработать смену пометки', InlineKeyboardMarkup([])

    new_ikb = list(source_keyboard)
    old_button = source_keyboard[pushed_row_index][0]
    new_mark_value, flash_message = _get_new_button_state_and_message(old_button)
    new_button = InlineKeyboardButton(
        text=new_mark_value + old_button.text[2:],
        callback_data=old_button.callback_data,
    )
    new_ikb[pushed_row_index] = [new_button, new_ikb[pushed_row_index][1]]

    db().record_search_whiteness(update_params.user_id, search_num, new_mark_value)
    tg_api().send_callback_answer_to_api(update_params.user_id, update_params.callback_query_id, flash_message)

    #        if pushed_row_index %2 ==0:##redundant because there is if user_used_inline_button
    #            api_callback_edit_inline_keyboard(bot_token, callback_query, reply_markup, user_id)

    # TODO should we remove old message and keyboard?
    bot_message = callback_query.message.text  # type:ignore [assignment,union-attr]
    return bot_message, InlineKeyboardMarkup(new_ikb)


def _get_new_button_state_and_message(button_to_change: InlineKeyboardButton) -> tuple[str, str]:
    old_mark_value = button_to_change.text[:2]

    transitions = {
        SearchFollowingMode.ON: (SearchFollowingMode.OFF, 'Поиск добавлен в черный список.'),
        SearchFollowingMode.OFF: (NOT_FOLLOWING_MARK, 'Пометка снята.'),
        NOT_FOLLOWING_MARK: (SearchFollowingMode.ON, 'Поиск добавлен в белый список.'),
    }
    return transitions[old_mark_value]


def _get_pressed_button_row_index(markup: InlineKeyboardMarkup, pressed_button_hash: int) -> int | None:
    ikb = markup.inline_keyboard
    for index, ikb_row in enumerate(ikb):
        logging.info(f'{ikb_row=}')
        if ikb_row[0].callback_data:
            button_data = literal_eval(str(ikb_row[0].callback_data))
            # Check if the pushed button matches the one in the callback

            if button_data.get('hash') and int(button_data['hash']) == pressed_button_hash:
                return index

    return None
