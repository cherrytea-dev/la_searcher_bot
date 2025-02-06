import base64
import datetime
import logging
import pickle
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import sleep
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup
from telegram import Bot, ReplyKeyboardMarkup
from telegram.ext import Application, ContextTypes

from _dependencies.commons import get_app_config, setup_google_logging, sql_connect_by_psycopg2
from _dependencies.misc import process_sending_message_async

COOKIE_FILE_NAME = 'session_cookies.pkl'

setup_google_logging()


@dataclass
class ForumUser:
    user_id: Any = None
    username: Any = None
    callsign: Any = None
    region: Any = None
    phone: Any = None
    auto_num: Any = None
    age: Any = None
    sex: Any = None
    reg_date: Any = None
    firstname: Any = None
    lastname: Any = None


@lru_cache
def get_session() -> requests.Session:
    session = requests.Session()
    load_cookies(session)
    return session


def load_cookies(session: requests.Session) -> None:
    pass
    # try:
    #     with open(COOKIE_FILE_NAME, 'rb') as f:
    #         session.cookies.update(pickle.load(f))
    #         logging.info('Cookies loaded from file')
    # except Exception:
    #     logging.warning('cannot load cookies')


def save_cookies(session: requests.Session) -> None:
    pass
    # with open(COOKIE_FILE_NAME, 'wb') as f:
    #     pickle.dump(session.cookies, f)


def login_into_forum() -> None:
    """login in into the forum"""

    logging.info('Trying to login to the forum')

    session = get_session()

    forum_bot_login = get_app_config().forum_bot_login
    forum_bot_password = get_app_config().forum_bot_password

    login_page = 'https://lizaalert.org/forum/ucp.php?mode=login'
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = {'username': forum_bot_login, 'password': forum_bot_password, 'login': 'Вход'}

    response = session.get(login_page)

    content = response.content.decode('utf-8')

    creation_time_match = re.compile(r'<input.*?name="creation_time".*?value="([^"]*)".*?/>').search(content)
    if creation_time_match:
        data.update({'creation_time': creation_time_match.group(1)})

    redirect_match = re.compile(r'<input.*?name="redirect".*?value="([^"]*)".*?/>').search(content)
    if redirect_match:
        data.update({'redirect': redirect_match.group(1)})

    sid_match = re.compile(r'<input.*?name="sid".*?value="([^"]*)".*?/>').search(content)
    if sid_match:
        data.update({'sid': sid_match.group(1)})

    form_token_match = re.compile(r'<input.*?name="form_token".*?value="([^"]*)".*?/>').search(content)
    if form_token_match:
        data.update({'form_token': form_token_match.group(1)})

    form_data = urllib.parse.urlencode(data)

    sleep(1)  # без этого не сработает %)
    r = session.post(login_page, headers=headers, data=form_data)

    if is_logged_in(r.text):
        logging.info('Logged in successfully')
        save_cookies(session)
    else:
        logging.exception('Login Failed')


def is_logged_in(response_text: str) -> bool:
    return 'Личные сообщения' in response_text


def get_user_id(u_name: str) -> str:
    """get user_id from forum"""

    user_id = ''
    forum_prefix = 'https://lizaalert.org/forum/memberlist.php?username='
    user_search_page = forum_prefix + u_name

    r2 = get_session().get(user_search_page)
    if not is_logged_in(r2.text):
        login_into_forum()
        r2 = get_session().get(user_search_page)

    soup = BeautifulSoup(r2.content, features='html.parser')

    try:
        block_with_username = soup.find('a', {'class': 'username'})
        if block_with_username is None:
            block_with_username = soup.find('a', {'class': 'username-coloured'})

        if block_with_username is not None:
            u_string = str(block_with_username)
            user_id = u_string[u_string.find(';u=') + 3 : u_string.find('">')]
            if user_id.find('style="color:') != -1:
                user_id = user_id[: (user_id.find('style="color:') - 2)]
            logging.info('User found, user_id=%s', user_id)
        else:
            logging.info('User not found')

    except Exception as e:
        logging.exception('User not found')

    return user_id


def get_user_attributes(user_id: str):
    """get user data from forum"""

    url_prefix = 'https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='
    r3 = get_session().get(url_prefix + user_id)
    soup = BeautifulSoup(r3.content, features='html.parser')
    block_with_user_attr = soup.find('div', {'class': 'page-body'})

    return block_with_user_attr


def get_user_data(data) -> ForumUser:
    """aggregates User Profile from forums' data"""

    user = ForumUser()

    dict = {
        'age': 'Возраст:',
        'sex': 'Пол:',
        'region': 'Регион:',
        'phone': 'Мобильный телефон:',
        'reg_date': 'Зарегистрирован:',
        'callsign': 'Позывной:',
    }

    for attr in dict:
        try:
            value = data.find('dt', text=dict[attr]).findNext('dd').text
            setattr(user, attr, value)
        except Exception as e1:
            logging.warning('Attribute {%s} is not defined', attr)
            logging.info(e1)

    return user


def match_user_region_from_forum_to_bot(forum_region: str) -> str | None:
    region_dict = {
        'Амурская область': 'Амурская обл.',
        'Астраханская область': 'Астраханская обл.',
        'Алтайский край': 'Алтайский край',
        'Брянская область': 'Брянская обл.',
        'Волгоградская область': 'Волгоградская обл.',
        'Воронежская область': 'Воронежская обл.',
        'Забайкальский край': None,
        'Иркутская область': 'Иркутская обл.',
        'Калининградская область': None,
        'Камчатский край': None,
        'Кемеровская область': 'Кемеровская обл.',
        'Костромская область': 'Костромская обл.',
        'Краснодарский край': 'Краснодарский край',
        'Красноярский край': 'Красноярский край',
        'Курганская область': 'Курганская обл.',
        'Курская область': 'Курская обл.',
        'Ленинградская область': 'Питер и ЛО',
        'Липецкая область': 'Липецкая обл.',
        'Магаданская область': None,
        'Мурманская область': 'Мурманская обл.',
        'Новгородская область': None,
        'Омская область': 'Омская обл.',
        'Орловская область': 'Орловская обл.',
        'Пермский край': 'Пермский край',
        'Псковская область': 'Псковская обл.',
        'Респ. Башкортостан': 'Башкортостан',
        'Респ. Дагестан': 'Дагестан',
        'Респ. Калмыкия': None,
        'Респ. Коми': 'Коми',
        'Респ. Марий Эл': 'Марий Эл',
        'Респ. Мордовия': 'Мордовия',
        'Респ. Саха (Якутия)': None,
        'Респ. Татарстан': 'Татарстан',
        'Респ. Тыва': None,
        'Республика Крым': 'Крым',
        'Ростовская область': 'Ростовская обл.',
        'Самарская область': 'Самарская обл.',
        'Сахалинская область': None,
        'Северная Осетия': 'Северная Осетия',
        'Ставропольский край': 'Ставропольский край',
        'Тверская область': 'Тверская обл.',
        'Томская область': 'Томская обл.',
        'Тульская область': 'Тульская обл.',
        'Тюменская область': 'Тюменская обл.',
        'Ульяновская область': 'Ульяновская обл.',
        'Челябинская область': 'Челябинская обл.',
        'Чувашская Респ.': 'Чувашия',
        'Чукотский округ': None,
        'Ярославская область': 'Ярославская обл.',
        'Другое': None,
        'ХМАО': 'Ханты-Мансийский АО',
        'ЯНАО': 'Ямало-Ненецкий АО',
    }

    try:
        bot_region = region_dict[forum_region]
    except Exception as e:
        logging.exception(e)
        bot_region = None

    return bot_region


# def save_user_region(user_id, region_name):
#    return None


def main(event: Dict[str, bytes], context: str) -> None:
    """main function triggered from communicate script via pyb/sub"""

    conn = sql_connect_by_psycopg2()
    cur = conn.cursor()

    pubsub_message = base64.b64decode(event['data']).decode('utf-8')

    encoded_to_ascii = eval(pubsub_message)
    data_in_ascii = encoded_to_ascii['data']
    message_in_ascii = data_in_ascii['message']
    tg_user_id, f_username = list(message_in_ascii)

    # initiate Prod Bot
    bot_token = get_app_config().bot_api_token__prod
    bot = Bot(token=bot_token)  # noqa

    user = None
    if message_in_ascii:
        f_usr_id = get_user_id(f_username)

        if f_usr_id != 0:
            block_of_user_data = get_user_attributes(f_usr_id)

            if block_of_user_data:
                user = get_user_data(block_of_user_data)

    if user:
        bot_message = 'Посмотрите, Бот нашел следующий аккаунт на форуме, это Вы?\n'
        bot_message += 'username: ' + f_username + ', '
        if user.callsign:
            bot_message += 'позывной: ' + user.callsign + ', '
        # if user.region:
        #     bot_message += 'регион: ' + user.region + ', '
        if user.phone:
            bot_message += 'телефон оканчивается на ' + str(user.phone)[-5:] + ', '
        if user.age:
            bot_message += 'возраст: ' + str(user.age) + ', '
        if user.reg_date:
            bot_message += 'дата регистрации: ' + str(user.reg_date)[:-7] + ', '
        bot_message = bot_message[:-2]

        keyboard = [['да, это я'], ['нет, это не я'], ['в начало']]

        # Delete previous records for this user
        cur.execute("""DELETE FROM user_forum_attributes WHERE user_id=%s;""", (tg_user_id,))
        conn.commit()

        # Add new record for this user
        cur.execute(
            """INSERT INTO user_forum_attributes
        (user_id, forum_user_id, status, timestamp, forum_username, forum_age, forum_sex, forum_region,
        forum_auto_num, forum_callsign, forum_phone, forum_reg_date)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);""",
            (
                tg_user_id,
                f_usr_id,
                'non-varified',
                datetime.datetime.now(),
                f_username,
                user.age,
                user.sex,
                user.region,
                user.auto_num,
                user.callsign,
                user.phone,
                user.reg_date,
            ),
        )
        conn.commit()

        cur.execute("""SELECT forum_folder_num FROM user_regional_preferences WHERE user_id=%s""", (tg_user_id,))
        conn.commit()
        user_has_region_set = True if cur.fetchone() else False
        logging.info(f'user_has_region_set = {user_has_region_set}')

        if not user_has_region_set and user.region:
            resulting_region_in_bot = match_user_region_from_forum_to_bot(user.region)  # noqa

        # TODO - here should be a block for saving user region pref. now we cannot do it, cuz user prefs are
        #  on folder level
        # if resulting_region_in_bot:
        # TODO ^^^

    else:
        bot_message = (
            'Бот не смог найти такого пользователя на форуме. '
            'Пожалуйста, проверьте правильность написания имени пользователя (логина). '
            'Важно, чтобы каждый знак в точности соответствовал тому, что указано в вашем профиле на форуме'
        )
        keyboard = [['в начало']]
        bot_request_aft_usr_msg = 'input_of_forum_username'

        try:
            cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (tg_user_id,))
            conn.commit()
            cur.execute(
                """
                INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);
                """,
                (tg_user_id, datetime.datetime.now(), bot_request_aft_usr_msg),
            )
            conn.commit()

        except Exception as e:
            logging.info('failed to update the last saved message from bot')
            logging.exception(e)

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    data = {'text': bot_message, 'reply_markup': reply_markup, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
    process_sending_message_async(user_id=tg_user_id, data=data)

    # save bot's reply to incoming request
    if bot_message:
        cur.execute(
            """INSERT INTO dialogs (user_id, author, timestamp, message_text) values (%s, %s, %s, %s);""",
            (tg_user_id, 'bot', datetime.datetime.now(), bot_message),
        )
        conn.commit()

    cur.close()
    conn.close()
