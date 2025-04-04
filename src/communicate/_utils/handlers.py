import logging
import re
from typing import Optional, Tuple, Union

from telegram import CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from _dependencies.commons import Topics, publish_to_pubsub
from _dependencies.misc import notify_admin, process_sending_message_async
from communicate._utils.buttons import (
    CoordinateSettingsMenu,
    MainSettingsMenu,
    NotificationSettingsMenu,
    b_act_titles,
    b_back_to_start,
    b_coords_auto_def,
    b_goto_community,
    b_goto_first_search,
    b_goto_photos,
    b_view_latest_searches,
)
from communicate._utils.common import (
    AgePeriod,
    AllButtons,
    SearchFollowingMode,
    UpdateBasicParams,
    if_user_enables,
    save_onboarding_step,
)
from communicate._utils.compose_messages import compose_user_preferences_message
from communicate._utils.database import db
from communicate._utils.message_sending import make_api_call, process_leaving_chat_async, send_callback_answer_to_api
from communicate.main import generate_yandex_maps_place_link


def manage_age(user_id: int, user_input: Optional[str]) -> None:
    """Save user Age preference and generate the list of updated Are preferences"""

    age_list = get_default_age_period_list()

    if user_input:
        user_want_activate = True if re.search(r'(?i)включить', user_input) else False
        user_new_setting = re.sub(r'.*чить: ', '', user_input)

        chosen_setting = None
        for line in age_list:
            if user_new_setting == line.description:
                chosen_setting = line
                break

        if user_want_activate:
            db().save_user_age_prefs(user_id, chosen_setting)
        else:
            db().delete_user_age_pref(user_id, chosen_setting)

    # Block for Generating a list of Buttons
    raw_list_of_periods = db().get_age_prefs(user_id)
    first_visit = False

    if raw_list_of_periods and str(raw_list_of_periods) != 'None':
        for line_raw in raw_list_of_periods:
            got_min, got_max = int(list(line_raw)[0]), int(list(line_raw)[1])
            for line_a in age_list:
                if int(line_a.min_age) == got_min and int(line_a.max_age) == got_max:
                    line_a.current = True
    else:
        first_visit = True
        for line_a in age_list:
            line_a.current = True
        for line in age_list:
            db().save_user_age_prefs(user_id, line)

    list_of_buttons = []
    for line in age_list:
        if line.current:
            list_of_buttons.append([f'отключить: {line.description}'])
        else:
            list_of_buttons.append([f'включить: {line.description}'])

    return list_of_buttons, first_visit


def get_default_age_period_list() -> list[AgePeriod]:
    return [
        AgePeriod(description='Маленькие Дети 0-6 лет', name='0-6', min_age=0, max_age=6, order=0),
        AgePeriod(description='Подростки 7-13 лет', name='7-13', min_age=7, max_age=13, order=1),
        AgePeriod(description='Молодежь 14-20 лет', name='14-20', min_age=14, max_age=20, order=2),
        AgePeriod(description='Взрослые 21-50 лет', name='21-50', min_age=21, max_age=50, order=3),
        AgePeriod(description='Старшее Поколение 51-80 лет', name='51-80', min_age=51, max_age=80, order=4),
        AgePeriod(description='Старцы более 80 лет', name='80-on', min_age=80, max_age=120, order=5),
    ]


def manage_radius(
    user_id: int,
    user_input: str,
    b_menu: str,
    b_act: str,
    b_deact: str,
    b_change: str,
    b_back: str,
    b_home_coord: str,
    expect_before: str,
) -> Tuple[str, ReplyKeyboardMarkup, None]:
    """Save user Radius preference and generate the actual radius preference"""

    list_of_buttons = []
    expect_after = None
    bot_message = None
    reply_markup_needed = True

    if user_input:
        if user_input.lower() == b_menu:
            saved_radius = db().check_saved_radius(user_id)
            if saved_radius:
                list_of_buttons = [[b_change], [b_deact], [b_home_coord], [b_back]]
                bot_message = (
                    f'Сейчас вами установлено ограничение радиуса {saved_radius} км. '
                    f'Вы в любой момент можете изменить или снять это ограничение.\n\n'
                    'ВАЖНО! Вы всё равно будете проинформированы по всем поискам, по которым '
                    'Бот не смог распознать никакие координаты.\n\n'
                    'Также, бот в первую очередь '
                    'проверяет расстояние от штаба, а если он не указан, то до ближайшего '
                    'населенного пункта (или топонима), указанного в теме поиска. '
                    'Расстояние считается по прямой.'
                )
            else:
                list_of_buttons = [[b_act], [b_home_coord], [b_back]]
                bot_message = (
                    'Данная настройка позволяет вам ограничить уведомления от бота только теми поисками, '
                    'для которых расстояние от ваших "домашних координат" до штаба/города '
                    'не превышает указанного вами Радиуса.\n\n'
                    'ВАЖНО! Вы всё равно будете проинформированы по всем поискам, по которым '
                    'Бот не смог распознать никакие координаты.\n\n'
                    'Также, Бот в первую очередь '
                    'проверяет расстояние от штаба, а если он не указан, то до ближайшего '
                    'населенного пункта (или топонима), указанного в теме поиска. '
                    'Расстояние считается по прямой.'
                )

        elif user_input in {b_act, b_change}:
            expect_after = 'radius_input'
            reply_markup_needed = False
            saved_radius = db().check_saved_radius(user_id)
            if saved_radius:
                bot_message = (
                    f'У вас установлено максимальное расстояние до поиска {saved_radius}.'
                    f'\n\nВведите обновлённое расстояние в километрах по прямой в формате простого '
                    f'числа (например: 150) и нажмите обычную кнопку отправки сообщения'
                )
            else:
                bot_message = (
                    'Введите расстояние в километрах по прямой в формате простого числа '
                    '(например: 150) и нажмите обычную кнопку отправки сообщения'
                )

        elif user_input == b_deact:
            list_of_buttons = [[b_act], [b_menu], [b_back]]
            db().delete_user_saved_radius(user_id)
            bot_message = 'Ограничение на расстояние по поискам снято!'

        elif expect_before == 'radius_input':
            number = re.search(r'[0-9]{1,6}', str(user_input))
            if number:
                number = int(number.group())
            if number and number > 0:
                db().save_user_radius(user_id, number)
                saved_radius = db().check_saved_radius(user_id)
                bot_message = (
                    f'Сохранили! Теперь поиски, у которых расстояние до штаба, '
                    f'либо до ближайшего населенного пункта (топонима) превосходит '
                    f'{saved_radius} км по прямой, не будут вас больше беспокоить. '
                    f'Настройку можно изменить в любое время.'
                )
                list_of_buttons = [[b_change], [b_deact], [b_menu], [b_back]]
            else:
                bot_message = 'Не могу разобрать цифры. Давайте еще раз попробуем?'
                list_of_buttons = [[b_act], [b_menu], [b_back]]

    if reply_markup_needed:
        reply_markup = ReplyKeyboardMarkup(list_of_buttons, resize_keyboard=True)
    else:
        reply_markup = ReplyKeyboardRemove()

    return bot_message, reply_markup, expect_after


def manage_topic_type(
    user_id: int,
    user_input: str,
    b: AllButtons,
    user_callback: dict,
    callback_id: str,
    bot_token: str,
    callback_query_msg_id: str,
) -> Union[tuple[None, None], tuple[str, ReplyKeyboardMarkup]]:
    """Save user Topic Type preference and generate the actual topic type preference message"""

    if not user_input:
        return None, None

    list_of_current_setting_ids = db().check_saved_topic_types(user_id)

    welcome_message = (
        'Вы можете выбрать и в любой момент поменять, по каким типам поисков или '
        'мероприятий бот должен присылать уведомления.'
    )

    # when user push "ABOUT" button
    if user_callback and user_callback['action'] == 'about':
        # this scenario assumes three steps: 1. send the "ABOUT" message, 2. delete prev MENU message 3. send NEW MENU
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
        make_api_call('sendMessage', bot_token, about_params, "main() if ... user_callback['action'] == 'about'")
        del_message_id = callback_query_msg_id  ###was get_last_user_inline_dialogue( user_id)
        if del_message_id:
            del_params = {'chat_id': user_id, 'message_id': del_message_id}
            make_api_call('deleteMessage', bot_token, del_params)
            user_input = b.set.topic_type.text  # to re-establish menu sending
            welcome_message = f'⬆️ Справка приведена выше. \n\n{welcome_message}'

    # when user just enters the MENU for topic types
    if user_input == b.set.topic_type.text:
        bot_message = welcome_message
        list_of_ids_to_change_now = []

    # when user pushed INLINE BUTTON for topic type
    else:
        topic_id = b.topic_types.button_by_hash(user_callback['hash']).id
        list_of_ids_to_change_now = [topic_id]
        user_wants_to_enable = if_user_enables(user_callback)
        if user_wants_to_enable is None:
            bot_message = ''
            pass
        elif user_wants_to_enable is True:  # not a poor design – function can be: None, True, False   # noqa
            bot_message = 'Супер, мы включили эти уведомления'
            send_callback_answer_to_api(bot_token, callback_id, bot_message)
            db().record_topic_type(user_id, topic_id)
        else:  # user_wants_to_enable == False:  # not a poor design – function can be: None, True, False # noqa
            if len(list_of_current_setting_ids) == 1:
                bot_message = '❌ Необходима как минимум одна настройка'
                list_of_ids_to_change_now = []
                send_callback_answer_to_api(bot_token, callback_id, bot_message)
            else:
                bot_message = 'Хорошо, мы изменили список настроек'
                send_callback_answer_to_api(bot_token, callback_id, bot_message)
                db().delete_user_saved_topic_type(user_id, topic_id)

    keyboard = b.topic_types.keyboard(act_list=list_of_current_setting_ids, change_list=list_of_ids_to_change_now)
    reply_markup = InlineKeyboardMarkup(keyboard)

    logging.info(f'{list_of_current_setting_ids=}')
    logging.info(f'{user_input=}')
    logging.info(f'{list_of_ids_to_change_now=}')
    logging.info(f'{keyboard=}')

    if user_input != b.set.topic_type.text:
        bot_message = welcome_message

    return bot_message, reply_markup


def manage_search_whiteness(
    user_id: int, user_callback: dict, callback_id: str, callback_query: CallbackQuery, bot_token: str
) -> Union[tuple[None, None], tuple[str, ReplyKeyboardMarkup]]:
    """Saves search_whiteness (accordingly to user's choice of search to follow) and regenerates the search list keyboard"""

    # issue#425 inspired by manage_topic_type
    ################# ToDo further: modify select in compose_notifications

    logging.info('callback_query=' + str(callback_query))
    logging.info(f'{user_id=}')
    # when user pushed INLINE BUTTON for topic following
    if user_callback and user_callback['action'] == 'search_follow_mode':
        # get inline keyboard from previous message to upadate it
        reply_markup = callback_query.message.reply_markup
        if reply_markup and not isinstance(reply_markup, dict):
            ikb = reply_markup.to_dict()['inline_keyboard']
        else:
            ikb = callback_query.message.reply_markup.inline_keyboard

        new_ikb = []
        logging.info(f'before for index, ikb_row in enumerate(ikb): {ikb=}')
        for index, ikb_row in enumerate(ikb):
            new_ikb += [ikb_row]
            logging.info(f'{ikb_row=}')
            if ikb_row[0].get('callback_data'):
                button_data = eval(ikb_row[0]['callback_data'])
                # Check if the pushed button matches the one in the callback
                if button_data.get('hash') and int(button_data['hash']) == int(user_callback['hash']):
                    pushed_row_index = index

        logging.info(f'before ikb_row = ikb[pushed_row_index]: {new_ikb=}')
        ikb_row = ikb[pushed_row_index]
        old_mark_value = ikb_row[0]['text'][:2]
        if old_mark_value == '  ':
            new_mark_value = SearchFollowingMode.ON
            bot_message = 'Поиск добавлен в белый список.'
        elif old_mark_value == SearchFollowingMode.ON:
            new_mark_value = SearchFollowingMode.OFF
            bot_message = 'Поиск добавлен в черный список.'
        else:
            new_mark_value = '  '
            bot_message = 'Пометка снята.'
        logging.info(f'before assign new_mark_value: {pushed_row_index=}, {old_mark_value=}, {new_mark_value=}')
        new_ikb[pushed_row_index][0]['text'] = new_mark_value + new_ikb[pushed_row_index][0]['text'][2:]
        # Update the search 'whiteness' (tracking state)
        db().record_search_whiteness(user_id, int(user_callback['hash']), new_mark_value)
        logging.info(f'before send_callback_answer_to_api: {new_ikb=}')
        send_callback_answer_to_api(bot_token, callback_id, bot_message)
        reply_markup = InlineKeyboardMarkup(new_ikb)
        logging.info(f'before api_callback_edit_inline_keyboard: {reply_markup=}')
        #        if pushed_row_index %2 ==0:##redundant because there is if user_used_inline_button
        #            api_callback_edit_inline_keyboard(bot_token, callback_query, reply_markup, user_id)

        bot_message = callback_query.message.text
    return bot_message, reply_markup


def manage_search_follow_mode(
    user_id: int, user_callback: dict, callback_id: str, callback_query, bot_token: str
) -> str | None:
    """Switches search following mode on/off"""

    logging.info(f'{callback_query=}, {user_id=}')
    # when user pushed INLINE BUTTON for topic following
    if user_callback and user_callback['action'] == 'search_follow_mode_on':
        db().set_search_follow_mode(user_id, True)
        bot_message = 'Режим выбора поисков для отслеживания включен.'

    elif user_callback and user_callback['action'] == 'search_follow_mode_off':
        db().set_search_follow_mode(user_id, False)
        bot_message = 'Режим выбора поисков для отслеживания отключен.'

    send_callback_answer_to_api(bot_token, callback_id, bot_message)

    return bot_message


def manage_if_moscow(
    user_id,
    username,
    got_message,
    b_reg_moscow,
    b_reg_not_moscow,
    reply_markup,
    keyboard_fed_dist_set,
    bot_message,
    user_role,
):
    """act if user replied either user from Moscow region or from another one"""

    # if user Region is Moscow
    if got_message == b_reg_moscow:
        save_onboarding_step(user_id, username, 'moscow_replied')
        save_onboarding_step(user_id, username, 'region_set')
        db().save_user_pref_topic_type(user_id, 'default', user_role)

        if db().check_if_user_has_no_regions(user_id):
            # add the New User into table user_regional_preferences
            # region is Moscow for Active Searches & InfoPod
            db().add_folder_to_user_regional_preference(user_id, 276)
            db().add_folder_to_user_regional_preference(user_id, 41)
            db().add_region_to_user_settings(user_id, 1)

    # if region is NOT Moscow
    elif got_message == b_reg_not_moscow:
        save_onboarding_step(user_id, username, 'moscow_replied')

        bot_message = (
            'Спасибо, тогда для корректной работы Бота, пожалуйста, выберите свой регион: '
            'сначала обозначьте Федеральный Округ, '
            'а затем хотя бы один Регион поисков, чтобы отслеживать поиски в этом регионе. '
            'Вы в любой момент сможете изменить '
            'список регионов через настройки бота.'
        )
        reply_markup = ReplyKeyboardMarkup(keyboard_fed_dist_set, resize_keyboard=True)

    else:
        bot_message = None
        reply_markup = None

    return bot_message, reply_markup


def manage_linking_to_forum(
    got_message: str,
    user_id: int,
    b_set_forum_nick: str,
    b_back_to_start: str,
    bot_request_bfr_usr_msg: str,
    b_admin_menu: str,
    b_test_menu: str,
    b_yes_its_me: str,
    b_no_its_not_me: str,
    b_settings: str,
    reply_markup_main: ReplyKeyboardMarkup,
) -> Tuple[str, ReplyKeyboardMarkup, Optional[str]]:
    """manage all interactions regarding connection of telegram and forum user accounts"""

    bot_message, reply_markup, bot_request_aft_usr_msg = None, None, None

    if got_message == b_set_forum_nick:
        # TODO: if user_is linked to forum so
        saved_forum_user = db().get_user_forum_attributes_db(user_id)

        if not saved_forum_user:
            bot_message = (
                'Бот сможет быть еще полезнее, эффективнее и быстрее, если указать ваш аккаунт на форуме '
                'lizaalert.org\n\n'
                'Для этого просто введите ответным сообщением своё имя пользователя (логин).\n\n'
                'Если возникнут ошибки при распознавании – просто скопируйте имя с форума и '
                'отправьте боту ответным сообщением.'
            )
            keyboard = [[b_back_to_start]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            bot_request_aft_usr_msg = 'input_of_forum_username'

        else:
            saved_forum_username, saved_forum_user_id = list(saved_forum_user)

            bot_message = (
                f'Ваш телеграм уже привязан к аккаунту '
                f'<a href="https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='
                f'{saved_forum_user_id}">{saved_forum_username}</a> '
                f'на форуме ЛизаАлерт. Больше никаких действий касательно аккаунта на форуме не требуется:)'
            )
            keyboard = [[b_settings], [b_back_to_start]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    elif (
        bot_request_bfr_usr_msg == 'input_of_forum_username'
        and got_message not in {b_admin_menu, b_back_to_start, b_test_menu}
        and len(got_message.split()) < 4
    ):
        message_for_pubsub = [user_id, got_message]
        publish_to_pubsub(Topics.parse_user_profile_from_forum, message_for_pubsub)
        bot_message = 'Сейчас посмотрю, это может занять до 10 секунд...'
        keyboard = [[b_back_to_start]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    elif got_message in {b_yes_its_me}:
        # Write "verified" for user
        db().write_user_forum_attributes_db(user_id)

        bot_message = (
            'Отлично, мы записали: теперь бот будет понимать, кто вы на форуме.\nЭто поможет '
            'вам более оперативно получать сообщения о поисках, по которым вы оставляли '
            'комментарии на форуме.'
        )
        keyboard = [[b_settings], [b_back_to_start]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    elif got_message == b_no_its_not_me:
        bot_message = (
            'Пожалуйста, тщательно проверьте написание вашего ника на форуме '
            '(кириллица/латиница, без пробела в конце) и введите его заново'
        )
        keyboard = [[b_set_forum_nick], [b_back_to_start]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        bot_request_aft_usr_msg = 'input_of_forum_username'

    elif got_message == b_back_to_start:
        bot_message = 'возвращаемся в главное меню'
        reply_markup = reply_markup_main

    return bot_message, reply_markup, bot_request_aft_usr_msg


def save_preference(user_id: int, preference: str):
    """Save user preference on types of notifications to be sent by bot"""

    # the master-table is dict_notif_types:

    if preference == 'all':
        db().user_preference_delete(user_id, [])
        db().user_preference_save(user_id, preference)

    elif preference in {
        'new_searches',
        'status_changes',
        'title_changes',
        'comments_changes',
        'first_post_changes',
        'all_in_followed_search',
    }:
        if db().user_preference_is_exists(user_id, ['all']):
            db().user_preference_save(user_id, 'bot_news')
        db().user_preference_delete(user_id, ['all'])

        db().user_preference_save(user_id, preference)

        if preference == 'comments_changes':
            db().user_preference_delete(user_id, ['inforg_comments'])

    elif preference == 'inforg_comments':
        if not db().user_preference_is_exists(user_id, ['all', 'comments_changes']):
            db().user_preference_save(user_id, preference)

    elif preference in {'field_trips_new', 'field_trips_change', 'coords_change'}:
        # FIXME – temp deactivation unlit feature will be ready for prod
        # FIXME – to be added to "new_searches" etc group
        # if not execute_check(user_id, ['all']):
        db().user_preference_save(user_id, preference)

    elif preference in {
        '-new_searches',
        '-status_changes',
        '-comments_changes',
        '-inforg_comments',
        '-title_changes',
        '-all',
        '-field_trips_new',
        '-field_trips_change',
        '-coords_change',
        '-first_post_changes',
        '-all_in_followed_search',
    }:
        if preference == '-all':
            db().user_preference_save(user_id, 'bot_news')
            db().user_preference_save(user_id, 'new_searches')
            db().user_preference_save(user_id, 'status_changes')
            db().user_preference_save(user_id, 'inforg_comments')
            db().user_preference_save(user_id, 'first_post_changes')
        elif preference == '-comments_changes':
            db().user_preference_save(user_id, 'inforg_comments')

        preference = preference[1:]
        db().user_preference_delete(user_id, [preference])


def handle_notification_settings(got_message: str, user_id: int) -> tuple[str, ReplyKeyboardMarkup]:
    if got_message == NotificationSettingsMenu.b_act_all:
        bot_message = (
            'Супер! теперь вы будете получать уведомления в телеграм в случаях: '
            'появление нового поиска, изменение статуса поиска (стоп, НЖ, НП), '
            'появление новых комментариев по всем поискам. Вы в любой момент '
            'можете изменить список уведомлений'
        )
        save_preference(user_id, 'all')

    # save preference for -ALL
    elif got_message == NotificationSettingsMenu.b_deact_all:
        bot_message = 'Вы можете настроить типы получаемых уведомлений более гибко'
        save_preference(user_id, '-all')

        # save preference for +NEW SEARCHES
    elif got_message == NotificationSettingsMenu.b_act_new_search:
        bot_message = (
            'Отлично! Теперь вы будете получать уведомления в телеграм при '
            'появлении нового поиска. Вы в любой момент можете изменить '
            'список уведомлений'
        )
        save_preference(user_id, 'new_searches')

        # save preference for -NEW SEARCHES
    elif got_message == NotificationSettingsMenu.b_deact_new_search:
        bot_message = 'Записали'
        save_preference(user_id, '-new_searches')

        # save preference for +STATUS UPDATES
    elif got_message == NotificationSettingsMenu.b_act_stat_change:
        bot_message = (
            'Отлично! теперь вы будете получать уведомления в телеграм при '
            'изменении статуса поисков (НЖ, НП, СТОП и т.п.). Вы в любой момент '
            'можете изменить список уведомлений'
        )
        save_preference(user_id, 'status_changes')

        # save preference for -STATUS UPDATES
    elif got_message == NotificationSettingsMenu.b_deact_stat_change:
        bot_message = 'Записали'
        save_preference(user_id, '-status_changes')

        # save preference for TITLE UPDATES
    elif got_message == b_act_titles:
        bot_message = 'Отлично!'
        save_preference(user_id, 'title_changes')

        # save preference for +COMMENTS
    elif got_message == NotificationSettingsMenu.b_act_all_comments:
        bot_message = (
            'Отлично! Теперь все новые комментарии будут у вас! Вы в любой момент ' 'можете изменить список уведомлений'
        )
        save_preference(user_id, 'comments_changes')

        # save preference for -COMMENTS
    elif got_message == NotificationSettingsMenu.b_deact_all_comments:
        bot_message = (
            'Записали. Мы только оставили вам включенными уведомления о '
            'комментариях Инфорга. Их тоже можно отключить'
        )
        save_preference(user_id, '-comments_changes')

        # save preference for +InforgComments
    elif got_message == NotificationSettingsMenu.b_act_inforg_com:
        bot_message = (
            'Если вы не подписаны на уведомления по всем комментариям, то теперь '
            'вы будете получать уведомления о комментариях от Инфорга. Если же вы '
            'уже подписаны на все комментарии – то всё остаётся без изменений: бот '
            'уведомит вас по всем комментариям, включая от Инфорга'
        )
        save_preference(user_id, 'inforg_comments')

        # save preference for -InforgComments
    elif got_message == NotificationSettingsMenu.b_deact_inforg_com:
        bot_message = 'Вы отписались от уведомлений по новым комментариям от Инфорга'
        save_preference(user_id, '-inforg_comments')

        # save preference for +FieldTripsNew
    elif got_message == NotificationSettingsMenu.b_act_field_trips_new:
        bot_message = (
            'Теперь вы будете получать уведомления о новых выездах по уже идущим '
            'поискам. Обратите внимание, что это не рассылка по новым темам на '
            'форуме, а именно о том, что в существующей теме в ПЕРВОМ посте '
            'появилась информация о новом выезде'
        )
        save_preference(user_id, 'field_trips_new')

        # save preference for -FieldTripsNew
    elif got_message == NotificationSettingsMenu.b_deact_field_trips_new:
        bot_message = 'Вы отписались от уведомлений по новым выездам'
        save_preference(user_id, '-field_trips_new')

        # save preference for +FieldTripsChange
    elif got_message == NotificationSettingsMenu.b_act_field_trips_change:
        bot_message = (
            'Теперь вы будете получать уведомления о ключевых изменениях при '
            'выездах, в т.ч. изменение или завершение выезда. Обратите внимание, '
            'что эта рассылка отражает изменения только в ПЕРВОМ посте поиска.'
        )
        save_preference(user_id, 'field_trips_change')

        # save preference for -FieldTripsChange
    elif got_message == NotificationSettingsMenu.b_deact_field_trips_change:
        bot_message = 'Вы отписались от уведомлений по изменениям выездов'
        save_preference(user_id, '-field_trips_change')

        # save preference for +CoordsChange
    elif got_message == NotificationSettingsMenu.b_act_coords_change:
        bot_message = (
            'Если у штаба поменяются координаты (и об этом будет написано в первом '
            'посте на форуме) – бот уведомит вас об этом'
        )
        save_preference(user_id, 'coords_change')

        # save preference for -CoordsChange
    elif got_message == NotificationSettingsMenu.b_deact_coords_change:
        bot_message = 'Вы отписались от уведомлений о смене места (координат) штаба'
        save_preference(user_id, '-coords_change')

        # save preference for +FirstPostChanges
    elif got_message == NotificationSettingsMenu.b_act_first_post_change:
        bot_message = (
            'Теперь вы будете получать уведомления о важных изменениях в Первом Посте'
            ' Инфорга, где обозначено описание каждого поиска'
        )
        save_preference(user_id, 'first_post_changes')

        # save preference for -FirstPostChanges
    elif got_message == NotificationSettingsMenu.b_deact_first_post_change:
        bot_message = (
            'Вы отписались от уведомлений о важных изменениях в Первом Посте' ' Инфорга c описанием каждого поиска'
        )
        save_preference(user_id, '-first_post_changes')

        # save preference for +all_in_followed_search
    elif got_message == NotificationSettingsMenu.b_act_all_in_followed_search:
        bot_message = 'Теперь во время отслеживания поиска будут все уведомления по нему.'
        save_preference(user_id, 'all_in_followed_search')

        # save preference for -all_in_followed_search
    elif got_message == NotificationSettingsMenu.b_deact_all_in_followed_search:
        bot_message = 'Теперь по отслеживаемым поискам будут уведомления как обычно (только настроенные).'
        save_preference(user_id, '-all_in_followed_search')

        # GET what are preferences
    elif got_message == MainSettingsMenu.b_set_pref_notif_type:
        prefs = compose_user_preferences_message(user_id)
        if prefs[0] == 'пока нет включенных уведомлений' or prefs[0] == 'неизвестная настройка':
            bot_message = 'Выберите, какие уведомления вы бы хотели получать'
        else:
            bot_message = 'Сейчас у вас включены следующие виды уведомлений:\n'
            bot_message += prefs[0]

    else:
        bot_message = 'empty message'

    if got_message == NotificationSettingsMenu.b_act_all:
        keyboard_notifications_flexible = [[NotificationSettingsMenu.b_deact_all], [b_back_to_start]]
    elif got_message == NotificationSettingsMenu.b_deact_all:  ##default state?
        keyboard_notifications_flexible = [
            [NotificationSettingsMenu.b_act_all],
            [NotificationSettingsMenu.b_deact_new_search],
            [NotificationSettingsMenu.b_deact_stat_change],
            [NotificationSettingsMenu.b_act_all_comments],
            [NotificationSettingsMenu.b_deact_inforg_com],
            [NotificationSettingsMenu.b_deact_first_post_change],
            [NotificationSettingsMenu.b_act_all_in_followed_search],
            [b_back_to_start],
        ]
    else:
        # getting the list of user notification preferences
        prefs = compose_user_preferences_message(user_id)
        keyboard_notifications_flexible = [
            [NotificationSettingsMenu.b_act_all],
            [NotificationSettingsMenu.b_act_new_search],
            [NotificationSettingsMenu.b_act_stat_change],
            [NotificationSettingsMenu.b_act_all_comments],
            [NotificationSettingsMenu.b_act_inforg_com],
            [NotificationSettingsMenu.b_act_first_post_change],
            [NotificationSettingsMenu.b_act_all_in_followed_search],
            [b_back_to_start],
        ]

        for line in prefs[1]:
            if line == 'all':
                keyboard_notifications_flexible = [
                    [NotificationSettingsMenu.b_deact_all],
                    [b_back_to_start],
                ]
            elif line == 'new_searches':
                keyboard_notifications_flexible[1] = [NotificationSettingsMenu.b_deact_new_search]
            elif line == 'status_changes':
                keyboard_notifications_flexible[2] = [NotificationSettingsMenu.b_deact_stat_change]
            elif line == 'comments_changes':
                keyboard_notifications_flexible[3] = [NotificationSettingsMenu.b_deact_all_comments]
            elif line == 'inforg_comments':
                keyboard_notifications_flexible[4] = [NotificationSettingsMenu.b_deact_inforg_com]
            elif line == 'first_post_changes':
                keyboard_notifications_flexible[5] = [NotificationSettingsMenu.b_deact_first_post_change]
            elif line == 'all_in_followed_search':
                keyboard_notifications_flexible[6] = [NotificationSettingsMenu.b_deact_all_in_followed_search]

    reply_markup = ReplyKeyboardMarkup(keyboard_notifications_flexible, resize_keyboard=True)
    return bot_message, reply_markup


def process_unneeded_messages(update, update_params: UpdateBasicParams) -> bool:
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
        data = {'text': bot_message}
        process_sending_message_async(user_id=user_id, data=data)
        return True

    # CASE 4 – when some Channel writes to bot
    if update_params.channel_type and user_id < 0:
        notify_admin('[comm]: INFO: CHANNEL sends messages to bot!')

        try:
            process_leaving_chat_async(user_id)
            notify_admin(f'[comm]: INFO: we have left the CHANNEL {user_id}')

        except Exception as e:
            logging.exception(f'[comm]: Leaving channel was not successful: {user_id}')
            notify_admin(f'[comm]: Leaving channel was not successful: {user_id}')
        return True

    # CASE 5 – when user sends Contact
    if update_params.contact:
        bot_message = (
            'Спасибо, буду знать. Вот только бот не работает с контактами и отвечает '
            'только на определенные текстовые команды.'
        )
        data = {'text': bot_message}
        process_sending_message_async(user_id=user_id, data=data)
        return True

    # CASE 6 – when user mentions bot as @LizaAlert_Searcher_Bot in another telegram chat. Bot should do nothing
    if update_params.inline_query:
        notify_admin('[comm]: User mentioned bot in some chats')
        logging.info(f'bot was mentioned in other chats: {update}')

    return False


def handle_goto_photos():
    bot_message = (
        'Если вам хочется окунуться в атмосферу ПСР, приглашаем в замечательный '
        '<a href="https://t.me/+6LYNNEy8BeI1NGUy">телеграм-канал с красивыми фото с '
        'поисков</a>. Все фото – сделаны поисковиками во время настоящих ПСР.'
    )
    keyboard_other = [
        [b_view_latest_searches],
        [b_goto_community],
        [b_goto_first_search],
        [b_back_to_start],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)
    return bot_message, reply_markup


def handle_goto_first_search():
    bot_message = (
        'Если вы хотите стать добровольцем ДПСО «ЛизаАлерт», пожалуйста, '
        '<a href="https://lizaalert.org/forum/viewtopic.php?t=56934">'
        'посетите страницу форума</a>, там можно ознакомиться с базовой информацией '
        'для новичков и задать свои вопросы.'
        'Если вы готовитесь к своему первому поиску – приглашаем '
        '<a href="https://lizaalert.org/dvizhenie/novichkam/">ознакомиться с основами '
        'работы ЛА</a>. Всю теорию работы ЛА необходимо получать от специально '
        'обученных волонтеров ЛА. Но если у вас еще не было возможности пройти '
        'официальное обучение, а вы уже готовы выехать на поиск – этот ресурс '
        'для вас.'
    )
    keyboard_other = [
        [b_view_latest_searches],
        [b_goto_community],
        [b_goto_photos],
        [b_back_to_start],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)
    return bot_message, reply_markup


def handle_goto_community():
    bot_message = (
        'Бот можно обсудить с соотрядниками в '
        '<a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальном Чате '
        'в телеграм</a>. Там можно предложить свои идеи, указать на проблемы '
        'и получить быструю обратную связь от разработчика.'
    )
    keyboard_other = [
        [b_view_latest_searches],
        [b_goto_first_search],
        [b_goto_photos],
        [b_back_to_start],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)
    return bot_message, reply_markup


def handle_coordinates(user_id: int, got_message: str):
    if got_message == MainSettingsMenu.b_set_pref_coords:
        bot_message = (
            'АВТОМАТИЧЕСКОЕ ОПРЕДЕЛЕНИЕ координат работает только для носимых устройств'
            ' (для настольных компьютеров – НЕ работает: используйте, пожалуйста, '
            'кнопку ручного ввода координат). '
            'При автоматическом определении координат – нажмите на кнопку и '
            'разрешите определить вашу текущую геопозицию. '
            'Координаты, загруженные вручную или автоматически, будут считаться '
            'вашим "домом", откуда будут рассчитаны расстояние и '
            'направление до поисков.'
        )
        keyboard_coordinates_1 = [
            [b_coords_auto_def],
            [CoordinateSettingsMenu.b_coords_man_def],
            [CoordinateSettingsMenu.b_coords_check],
            [CoordinateSettingsMenu.b_coords_del],
            [b_back_to_start],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

    elif got_message == CoordinateSettingsMenu.b_coords_del:
        db().delete_user_coordinates(user_id)
        bot_message = (
            'Ваши "домашние координаты" удалены. Теперь расстояние и направление '
            'до поисков не будет отображаться.\n'
            'Вы в любой момент можете заново ввести новые "домашние координаты". '
            'Функция Автоматического определения координат работает только для '
            'носимых устройств, для настольного компьютера – воспользуйтесь '
            'ручным вводом.'
        )
        keyboard_coordinates_1 = [
            [b_coords_auto_def],
            [CoordinateSettingsMenu.b_coords_man_def],
            [CoordinateSettingsMenu.b_coords_check],
            [b_back_to_start],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

    elif got_message == CoordinateSettingsMenu.b_coords_man_def:
        bot_message = (
            'Введите координаты вашего дома вручную в теле сообщения и просто '
            'отправьте. Формат: XX.XXXХХ, XX.XXXХХ, где количество цифр после точки '
            'может быть различным. Широта (первое число) должна быть между 30 '
            'и 80, Долгота (второе число) – между 10 и 190.'
        )
        bot_request_aft_usr_msg = 'input_of_coords_man'
        reply_markup = ReplyKeyboardRemove()

    elif got_message == CoordinateSettingsMenu.b_coords_check:
        lat, lon = db().show_user_coordinates(user_id)
        if lat and lon:
            bot_message = 'Ваши "домашние координаты" '
            bot_message += generate_yandex_maps_place_link(lat, lon, 'coords')

        else:
            bot_message = 'Ваши координаты пока не сохранены. Введите их автоматически или вручную.'

        keyboard_coordinates_1 = [
            [b_coords_auto_def],
            [CoordinateSettingsMenu.b_coords_man_def],
            [CoordinateSettingsMenu.b_coords_check],
            [CoordinateSettingsMenu.b_coords_del],
            [b_back_to_start],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

    return bot_message, reply_markup, bot_request_aft_usr_msg
