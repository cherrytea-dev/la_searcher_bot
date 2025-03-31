import datetime
import re
from typing import Any, Optional, Tuple, Union

from psycopg2.extensions import cursor
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove


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
