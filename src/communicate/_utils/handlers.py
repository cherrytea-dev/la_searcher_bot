import datetime
import logging
import re
from typing import Any, Optional, Tuple, Union

from psycopg2.extensions import cursor
from telegram import CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from _dependencies.commons import Topics, publish_to_pubsub
from communicate._utils.common import AllButtons, SearchFollowingMode, if_user_enables, save_onboarding_step
from communicate._utils.database import (
    check_if_user_has_no_regions,
    get_user_forum_attributes_db,
    save_user_pref_topic_type,
    set_search_follow_mode,
    write_user_forum_attributes_db,
)
from communicate._utils.message_sending import make_api_call, send_callback_answer_to_api


def manage_age(cur: cursor, user_id: int, user_input: Optional[str]) -> None:
    """Save user Age preference and generate the list of updated Are preferences"""

    class AgePeriod:
        def __init__(
            self,
            description: str = None,
            name: str = None,
            current=None,
            min_age: int = None,
            max_age: int = None,
            order: int = None,
        ):
            self.desc = description
            self.name = name
            self.now = current
            self.min = min_age
            self.max = max_age
            self.order = order

    age_list = [
        AgePeriod(description='Маленькие Дети 0-6 лет', name='0-6', min_age=0, max_age=6, order=0),
        AgePeriod(description='Подростки 7-13 лет', name='7-13', min_age=7, max_age=13, order=1),
        AgePeriod(description='Молодежь 14-20 лет', name='14-20', min_age=14, max_age=20, order=2),
        AgePeriod(description='Взрослые 21-50 лет', name='21-50', min_age=21, max_age=50, order=3),
        AgePeriod(description='Старшее Поколение 51-80 лет', name='51-80', min_age=51, max_age=80, order=4),
        AgePeriod(description='Старцы более 80 лет', name='80-on', min_age=80, max_age=120, order=5),
    ]

    if user_input:
        user_want_activate = True if re.search(r'(?i)включить', user_input) else False
        user_new_setting = re.sub(r'.*чить: ', '', user_input)

        chosen_setting = None
        for line in age_list:
            if user_new_setting == line.desc:
                chosen_setting = line
                break

        if user_want_activate:
            cur.execute(
                """INSERT INTO user_pref_age (user_id, period_name, period_set_date, period_min, period_max) 
                        values (%s, %s, %s, %s, %s) ON CONFLICT (user_id, period_min, period_max) DO NOTHING;""",
                (user_id, chosen_setting.name, datetime.datetime.now(), chosen_setting.min, chosen_setting.max),
            )
        else:
            cur.execute(
                """DELETE FROM user_pref_age WHERE user_id=%s AND period_min=%s AND period_max=%s;""",
                (user_id, chosen_setting.min, chosen_setting.max),
            )

    # Block for Generating a list of Buttons
    cur.execute("""SELECT period_min, period_max FROM user_pref_age WHERE user_id=%s;""", (user_id,))
    raw_list_of_periods = cur.fetchall()
    first_visit = False

    if raw_list_of_periods and str(raw_list_of_periods) != 'None':
        for line_raw in raw_list_of_periods:
            got_min, got_max = int(list(line_raw)[0]), int(list(line_raw)[1])
            for line_a in age_list:
                if int(line_a.min) == got_min and int(line_a.max) == got_max:
                    line_a.now = True
    else:
        first_visit = True
        for line_a in age_list:
            line_a.now = True
        for line in age_list:
            cur.execute(
                """INSERT INTO user_pref_age (user_id, period_name, period_set_date, period_min, period_max) 
                        values (%s, %s, %s, %s, %s) ON CONFLICT (user_id, period_min, period_max) DO NOTHING;""",
                (user_id, line.name, datetime.datetime.now(), line.min, line.max),
            )

    list_of_buttons = []
    for line in age_list:
        if line.now:
            list_of_buttons.append([f'отключить: {line.desc}'])
        else:
            list_of_buttons.append([f'включить: {line.desc}'])

    return list_of_buttons, first_visit


def manage_radius(
    cur: cursor,
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

    def check_saved_radius(user: int) -> Optional[Any]:
        """check if user already has a radius preference"""

        saved_rad = None
        cur.execute("""SELECT radius FROM user_pref_radius WHERE user_id=%s;""", (user,))
        raw_radius = cur.fetchone()
        if raw_radius and str(raw_radius) != 'None':
            saved_rad = int(raw_radius[0])
        return saved_rad

    list_of_buttons = []
    expect_after = None
    bot_message = None
    reply_markup_needed = True

    if user_input:
        if user_input.lower() == b_menu:
            saved_radius = check_saved_radius(user_id)
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
            saved_radius = check_saved_radius(user_id)
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
            cur.execute("""DELETE FROM user_pref_radius WHERE user_id=%s;""", (user_id,))
            bot_message = 'Ограничение на расстояние по поискам снято!'

        elif expect_before == 'radius_input':
            number = re.search(r'[0-9]{1,6}', str(user_input))
            if number:
                number = int(number.group())
            if number and number > 0:
                cur.execute(
                    """INSERT INTO user_pref_radius (user_id, radius) 
                               VALUES (%s, %s) ON CONFLICT (user_id) DO
                               UPDATE SET radius=%s;""",
                    (user_id, number, number),
                )
                saved_radius = check_saved_radius(user_id)
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
    cur: cursor,
    user_id: int,
    user_input: str,
    b: AllButtons,
    user_callback: dict,
    callback_id: str,
    bot_token: str,
    callback_query_msg_id: str,
) -> Union[tuple[None, None], tuple[str, ReplyKeyboardMarkup]]:
    """Save user Topic Type preference and generate the actual topic type preference message"""

    def check_saved_topic_types(user: int) -> list:
        """check if user already has any preference"""

        saved_pref = []
        cur.execute("""SELECT topic_type_id FROM user_pref_topic_type WHERE user_id=%s ORDER BY 1;""", (user,))
        raw_data = cur.fetchall()
        if raw_data and str(raw_data) != 'None':
            for line in raw_data:
                saved_pref.append(line[0])

        logging.info(f'{saved_pref=}')

        return saved_pref

    def delete_topic_type(user: int, type_id: int) -> None:
        """Delete a certain topic_type for a certain user_id from the DB"""

        cur.execute("""DELETE FROM user_pref_topic_type WHERE user_id=%s AND topic_type_id=%s;""", (user, type_id))
        return None

    def record_topic_type(user: int, type_id: int) -> None:
        """Insert a certain topic_type for a certain user_id into the DB"""

        cur.execute(
            """INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp) 
                        VALUES (%s, %s, %s) ON CONFLICT (user_id, topic_type_id) DO NOTHING;""",
            (user, type_id, datetime.datetime.now()),
        )
        return None

    if not user_input:
        return None, None

    list_of_current_setting_ids = check_saved_topic_types(user_id)

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
        del_message_id = callback_query_msg_id  ###was get_last_user_inline_dialogue(cur, user_id)
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
            record_topic_type(user_id, topic_id)
        else:  # user_wants_to_enable == False:  # not a poor design – function can be: None, True, False # noqa
            if len(list_of_current_setting_ids) == 1:
                bot_message = '❌ Необходима как минимум одна настройка'
                list_of_ids_to_change_now = []
                send_callback_answer_to_api(bot_token, callback_id, bot_message)
            else:
                bot_message = 'Хорошо, мы изменили список настроек'
                send_callback_answer_to_api(bot_token, callback_id, bot_message)
                delete_topic_type(user_id, topic_id)

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
    cur: cursor, user_id: int, user_callback: dict, callback_id: str, callback_query: CallbackQuery, bot_token: str
) -> Union[tuple[None, None], tuple[str, ReplyKeyboardMarkup]]:
    """Saves search_whiteness (accordingly to user's choice of search to follow) and regenerates the search list keyboard"""

    # issue#425 inspired by manage_topic_type
    ################# ToDo further: modify select in compose_notifications

    def record_search_whiteness(user: int, search_id: int, new_mark_value) -> None:
        """Save a certain user_pref_search_whitelist for a certain user_id into the DB"""
        if new_mark_value in [SearchFollowingMode.ON, SearchFollowingMode.OFF]:
            cur.execute(
                """INSERT INTO user_pref_search_whitelist (user_id, search_id, timestamp, search_following_mode) 
                            VALUES (%s, %s, %s, %s) ON CONFLICT (user_id, search_id) DO UPDATE SET timestamp=%s, search_following_mode=%s;""",
                (user, search_id, datetime.datetime.now(), new_mark_value, datetime.datetime.now(), new_mark_value),
            )
        else:
            cur.execute(
                """DELETE FROM user_pref_search_whitelist WHERE user_id=%(user)s and search_id=%(search_id)s;""",
                {'user': user, 'search_id': search_id},
            )
        return None

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
        record_search_whiteness(user_id, int(user_callback['hash']), new_mark_value)
        logging.info(f'before send_callback_answer_to_api: {new_ikb=}')
        send_callback_answer_to_api(bot_token, callback_id, bot_message)
        reply_markup = InlineKeyboardMarkup(new_ikb)
        logging.info(f'before api_callback_edit_inline_keyboard: {reply_markup=}')
        #        if pushed_row_index %2 ==0:##redundant because there is if user_used_inline_button
        #            api_callback_edit_inline_keyboard(bot_token, callback_query, reply_markup, user_id)

        bot_message = callback_query.message.text
    return bot_message, reply_markup


def manage_search_follow_mode(
    cur: cursor, user_id: int, user_callback: dict, callback_id: str, callback_query, bot_token: str
) -> str | None:
    """Switches search following mode on/off"""

    logging.info(f'{callback_query=}, {user_id=}')
    # when user pushed INLINE BUTTON for topic following
    if user_callback and user_callback['action'] == 'search_follow_mode_on':
        set_search_follow_mode(cur, user_id, True)
        bot_message = 'Режим выбора поисков для отслеживания включен.'

    elif user_callback and user_callback['action'] == 'search_follow_mode_off':
        set_search_follow_mode(cur, user_id, False)
        bot_message = 'Режим выбора поисков для отслеживания отключен.'

    send_callback_answer_to_api(bot_token, callback_id, bot_message)

    return bot_message


def manage_if_moscow(
    cur,
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
        save_user_pref_topic_type(cur, user_id, 'default', user_role)

        if check_if_user_has_no_regions(cur, user_id):
            # add the New User into table user_regional_preferences
            # region is Moscow for Active Searches & InfoPod
            cur.execute(
                """INSERT INTO user_regional_preferences (user_id, forum_folder_num) values
                (%s, %s);""",
                (user_id, 276),
            )
            cur.execute(
                """INSERT INTO user_regional_preferences (user_id, forum_folder_num) values
                (%s, %s);""",
                (user_id, 41),
            )
            cur.execute(
                """INSERT INTO user_pref_region (user_id, region_id) values
                (%s, %s);""",
                (user_id, 1),
            )

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
    cur: cursor,
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
        saved_forum_user = get_user_forum_attributes_db(cur, user_id)

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
        write_user_forum_attributes_db(cur, user_id)

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
