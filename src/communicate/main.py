"""receives telegram messages from users, acts accordingly and sends back the reply"""

import datetime
import re
import json
import logging
import math
import psycopg2
import urllib.request
import urllib.parse
import requests
from typing import Union, Tuple

from google.cloud import secretmanager, pubsub_v1
import google.cloud.logging

import asyncio
from queue import Queue
from telegram import ReplyKeyboardMarkup, KeyboardButton, Bot, Update, ReplyKeyboardRemove, \
    InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, Application

publisher = pubsub_v1.PublisherClient()
url = "http://metadata.google.internal/computeMetadata/v1/project/project-id"
req = urllib.request.Request(url)
req.add_header("Metadata-Flavor", "Google")
project_id = urllib.request.urlopen(req).read().decode()
client = secretmanager.SecretManagerServiceClient()

log_client = google.cloud.logging.Client()
log_client.setup_logging()

# To get rid of telegram "Retrying" Warning logs, which are shown in GCP Log Explorer as Errors.
# Important – these are not errors, but jest informational warnings that there were retries, that's why we exclude them
logging.getLogger("telegram.vendor.ptb_urllib3.urllib3").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

full_buttons_dict = {
    'topic_types':
        {
            'regular': {
                'text': 'стандартные активные поиски',
                'id': 0},
            'reverse': {
                'text': 'обратные поиски (поиск родных)',
                'id': 1},
            'patrol': {
                'text': 'патруль (только для некоторых регионов)',
                'id': 2,
                'hide': True},
            'training': {
                'text': 'учебные поиски',
                'id': 3},
            'info_support': {
                'text': 'информационная поддержка поисков',
                'id': 4,
                'hide': True},
            'resonance': {
                'text': 'резонансные поиски в нескольких регионах',
                'id': 5,
                'hide': True},
            'event': {
                'text': 'мероприятия',
                'id': 10},
            'info': {
                'text': 'полезная информация',
                'id': 20,
                'hide': True},
         },
    'roles':
        {
            'member': {
                'text': 'я состою в ЛизаАлерт',
                'id': 'member'},
            'new_member': {
                'text': 'я хочу помогать ЛизаАлерт',
                'id': 'new_member'},
            'relative': {
                'text': 'я ищу человека',
                'id': 'relative'},
            'other': {
                'text': 'у меня другая задача',
                'id': 'other'},
            'no_answer': {
                'text': 'не хочу говорить',
                'id': 'no_answer'}
        },
    'set':
        {
            'topic_type': {
                'text': 'настроить вид интересующих поисков',
                'id': 'topic_type'}
        },
    'core':
        {
            'to_start': {
                'text': 'в начало',
                'id': 'to_start'
            }
        }
}


class SearchSummary:

    def __init__(self,
                 topic_type=None,
                 topic_id=None,
                 parsed_time=None,
                 status=None,
                 title=None,
                 link=None,
                 start_time=None,
                 num_of_replies=None,
                 name=None,
                 display_name=None,
                 age=None,
                 searches_table_id=None,
                 folder_id=None,
                 age_max=None,
                 age_min=None,
                 num_of_persons=None,
                 city_locations=None,
                 hq_locations=None,
                 new_status=None,
                 full_dict=None
                 ):
        self.topic_type = topic_type
        self.topic_id = topic_id
        self.parsed_time = parsed_time
        self.status = status
        self.title = title
        self.link = link
        self.start_time = start_time
        self.num_of_replies = num_of_replies
        self.name = name
        self.display_name = display_name
        self.age = age
        self.id = searches_table_id
        self.folder_id = folder_id
        self.age_max = age_max
        self.age_min = age_min
        self.num_of_persons = num_of_persons
        self.city_locations = city_locations  # city / town / place – approximate coordinates
        self.hq_locations = hq_locations  # shtab –exact coordinates
        self.new_status = new_status
        self.full_dict = full_dict

    def __str__(self):
        return f'{self.parsed_time} – {self.folder_id} / {self.topic_id} : {self.name} - {self.age} – ' \
               f'{self.num_of_replies}. NEW: {self.display_name} – {self.age_min} – {self.age_max} – ' \
               f'{self.num_of_persons}'


class Button:
    """Contains one unique button and all the associated attributes"""

    def __init__(self, data=None, modifier=None):

        if modifier is None:
            modifier = {'on': '☑ ', 'off': '☐ '}  # standard modifier

        self.modifier = modifier
        self.data = data
        self.text = None
        for key, value in self.data.items():
            setattr(self, key, value)

        self.any_text = [self.text]
        for key, value in modifier.items():
            new_value = f'{value}{self.text}'
            setattr(self, key, new_value)
            self.any_text.append(new_value)

        self.all = [v for k, v in self.__dict__.items() if v != modifier]

    def __str__(self):
        return self.text

    def temp_all_keys(self):
        return [k for k, v in self.__dict__.items()]


class GroupOfButtons:
    """Contains the set of unique buttons of the similar nature (to be shown together as alternatives)"""

    def __init__(self, button_dict, modifier_dict=None):

        self.modifier_dict = modifier_dict

        all_button_texts = []
        for key, value in button_dict.items():
            setattr(self, key, Button(value, modifier_dict))
            all_button_texts += self.__getattribute__(key).any_text
        self.any_text = all_button_texts

    def __str__(self):
        return self.any_text

    def contains(self, check):
        """Check is the given text is used for any button in this group"""

        if check in self.any_text:
            return True
        else:
            return False

    def temp_all_keys(self):
        return [k for k, v in self.__dict__.items()]

    def id(self, given_id):
        """Return a Button which correspond to the given id"""
        for key, value in self.__dict__.items():
            if not value:
                continue
            if hasattr(value, 'id') and value.id == given_id:
                return value
        return None

    def keyboard(self, act_list, change_list):
        """Generate a list of telegram buttons (2D array) basing on existing setting list and one that should change"""

        keyboard = []
        for key, value in self.__dict__.items():
            curr_button = self.__getattribute__(key)
            if key in {'modifier_dict', 'any_text'}:
                continue
            if hasattr(value, 'hide') and value.hide:
                continue
            curr_button_is_in_existing_id_list = False
            curr_button_is_asked_to_change = False
            for id_item in act_list:
                if curr_button.id == id_item:
                    curr_button_is_in_existing_id_list = True
                    break
            for id_item in change_list:
                if curr_button.id == id_item:
                    curr_button_is_asked_to_change = True
                    break

            if curr_button_is_in_existing_id_list:
                if not curr_button_is_asked_to_change:
                    keyboard += [
                        {"text": curr_button.on, 'callback_data': str({'action': 'off', 'button': curr_button.text})}]

                else:
                    keyboard += [
                        {"text": curr_button.off, 'callback_data': str({'action': 'on', 'button': curr_button.text})}]
            else:
                if not curr_button_is_asked_to_change:
                    keyboard += [
                        {"text": curr_button.off, 'callback_data': str({'action': 'on', 'button': curr_button.text})}]
                else:
                    keyboard += [
                        {"text": curr_button.on, 'callback_data': str({'action': 'off', 'button': curr_button.text})}]

        keyboard = [[k] for k in keyboard]

        return keyboard

    def button_by_text(self, given_text):
        """Return a Button which correspond to the given text"""
        for key, value in self.__dict__.items():
            if not value:
                continue
            if hasattr(value, 'any_text') and given_text in value.any_text:
                return value
        return None

class AllButtons:

    def __init__(self, initial_dict):

        for key, value in initial_dict.items():
            setattr(self, key, GroupOfButtons(value))

    def temp_all_keys(self):
        return [k for k, v in self.__dict__.items()]


def get_secrets(secret_request):
    """Get GCP secret"""

    name = f"projects/{project_id}/secrets/{secret_request}/versions/latest"
    response = client.access_secret_version(name=name)

    return response.payload.data.decode("UTF-8")


def sql_connect_by_psycopg2():
    """connect to GCP SLQ via PsycoPG2"""

    db_user = get_secrets("cloud-postgres-username")
    db_pass = get_secrets("cloud-postgres-password")
    db_name = get_secrets("cloud-postgres-db-name")
    db_conn = get_secrets("cloud-postgres-connection-name")
    db_host = '/cloudsql/' + db_conn

    conn_psy = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_pass)
    conn_psy.autocommit = True

    return conn_psy


def publish_to_pubsub(topic_name, message):
    """Publish a message to pub/sub"""

    # Prepare to turn to the existing pub/sub topic
    topic_path = publisher.topic_path(project_id, topic_name)

    # Prepare the message
    message_json = json.dumps({'data': {'message': message}, })
    message_bytes = message_json.encode('utf-8')

    # Publish the message
    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify that publishing succeeded
        logging.info(f'Pub/sub message was published: {message}')

    except Exception as e:
        logging.info('Pub/sub message was NOT published')
        logging.exception(e)

    return None


def notify_admin(message):
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub('topic_notify_admin', message)

    return None


def time_counter_since_search_start(start_time):
    """Count timedelta since the beginning of search till now, return phrase in Russian and diff in days """

    start_diff = datetime.timedelta(hours=0)

    now = datetime.datetime.now()
    diff = now - start_time - start_diff

    first_word_parameter = ''

    # <20 minutes -> "Начинаем искать"
    if (diff.total_seconds() / 60) < 20:
        phrase = 'Начинаем искать'

    # 20 min - 1 hour -> "Ищем ХХ минут"
    elif (diff.total_seconds() / 3600) < 1:
        phrase = first_word_parameter + str(round(int(diff.total_seconds() / 60), -1)) + ' минут'

    # 1-24 hours -> "Ищем ХХ часов"
    elif diff.days < 1:
        phrase = first_word_parameter + str(int(diff.total_seconds() / 3600))
        if int(diff.total_seconds() / 3600) in {1, 21}:
            phrase += ' час'
        elif int(diff.total_seconds() / 3600) in {2, 3, 4, 22, 23}:
            phrase += ' часа'
        else:
            phrase += ' часов'

    # >24 hours -> "Ищем Х дней"
    else:
        phrase = first_word_parameter + str(diff.days)
        if str(int(diff.days))[-1] == '1' and (int(diff.days)) != 11:
            phrase += ' день'
        elif int(diff.days) in {12, 13, 14}:
            phrase += ' дней'
        elif str(int(diff.days))[-1] in {'2', '3', '4'}:
            phrase += ' дня'
        else:
            phrase += ' дней'

    return [phrase, diff.days]


def age_writer(age):
    """Return age-describing phrase in Russian for age as integer"""

    a = age // 100
    b = (age - a * 100) // 10
    c = age - a * 100 - b * 10

    if c == 1 and b != 1:
        wording = str(age) + " год"
    elif (c in {2, 3, 4}) and b != 1:
        wording = str(age) + " года"
    else:
        wording = str(age) + " лет"

    return wording


def compose_user_preferences_message(cur, user_id):
    """Compose a text for user on which types of notifications are enabled for zir"""

    cur.execute("""SELECT preference FROM user_preferences WHERE user_id=%s ORDER BY preference;""", (user_id,))
    user_prefs = cur.fetchall()

    prefs_wording = ''
    prefs_list = []
    if user_prefs and len(user_prefs) > 0:
        for user_pref_line in user_prefs:
            prefs_list.append(user_pref_line[0])
            if user_pref_line[0] == 'all':
                prefs_wording += 'все сообщения'
            elif user_pref_line[0] == 'new_searches':
                prefs_wording += ' &#8226; о новых поисках\n'
            elif user_pref_line[0] == 'status_changes':
                prefs_wording += ' &#8226; об изменении статуса\n'
            elif user_pref_line[0] == 'title_changes':
                prefs_wording += ' &#8226; об изменении заголовка\n'
            elif user_pref_line[0] == 'comments_changes':
                prefs_wording += ' &#8226; о всех комментариях\n'
            elif user_pref_line[0] == 'inforg_comments':
                prefs_wording += ' &#8226; о комментариях Инфорга\n'
            elif user_pref_line[0] == 'first_post_changes':
                prefs_wording += ' &#8226; об изменениях в первом посте\n'
            elif user_pref_line[0] == 'bot_news':
                pass
            else:
                prefs_wording += 'неизвестная настройка'
    else:
        prefs_wording += 'пока нет включенных уведомлений'

    prefs_wording_and_list = [prefs_wording, prefs_list]

    return prefs_wording_and_list


def compose_msg_on_all_last_searches(cur, region):
    """Compose a part of message on the list of recent searches"""

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    text = ''

    # download the list from SEARCHES sql table
    cur.execute(
        """SELECT s2.* FROM 
            (SELECT search_forum_num, search_start_time, display_name, status, status, family_name, age 
            FROM searches 
            WHERE forum_folder_id=%s 
            ORDER BY search_start_time DESC 
            LIMIT 20) s2 
        LEFT JOIN search_health_check shc 
        ON s2.search_forum_num=shc.search_forum_num 
        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
        ORDER BY s2.search_start_time DESC;""", (region,))

    database = cur.fetchall()

    for line in database:
        search = SearchSummary()
        search.topic_id, search.start_time, search.display_name, search.new_status, \
            search.status, search.name, search.age = list(line)

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age and search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        if not search.new_status:
            search.new_status = search.status

        if search.new_status in {'Ищем', 'Возобновлен'}:
            search.new_status = f'Ищем {time_counter_since_search_start(search.start_time)[0]}'

        text += f'{search.new_status} <a href="{pre_url}{search.topic_id}">{search.display_name}</a>\n'

    return text


def compose_msg_on_active_searches_in_one_reg(cur, region, user_data):
    """Compose a part of message on the list of active searches in the given region with relation to user's coords"""

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    text = ''

    cur.execute(
        """SELECT s2.* FROM 
            (SELECT s.search_forum_num, s.search_start_time, s.display_name, sa.latitude, sa.longitude, 
            s.topic_type, s.family_name, s.age 
            FROM searches s 
            LEFT JOIN search_coordinates sa ON s.search_forum_num = sa.search_id 
            WHERE (s.status='Ищем' OR s.status='Возобновлен') 
                AND s.forum_folder_id=%s ORDER BY s.search_start_time DESC) s2 
        LEFT JOIN search_health_check shc ON s2.search_forum_num=shc.search_forum_num
        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
        ORDER BY s2.search_start_time DESC;""", (region,))
    searches_list = cur.fetchall()

    user_lat = None
    user_lon = None

    if user_data:
        user_lat = user_data[0]
        user_lon = user_data[1]

    for line in searches_list:
        search = SearchSummary()
        search.topic_id, search.start_time, search.display_name, search_lat, search_lon, \
        search.topic_type, search.name, search.age = list(line)

        if time_counter_since_search_start(search.start_time)[1] >= 60:
            continue

        time_since_start = time_counter_since_search_start(search.start_time)[0]

        if user_lat and search_lat:
            dist = distance_to_search(search_lat, search_lon, user_lat, user_lon)
            dist_and_dir = f' {dist[1]} {dist[0]} км'
        else:
            dist_and_dir = ''

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        text += f'{time_since_start}{dist_and_dir} <a href="{pre_url}{search.topic_id}">{search.display_name}</a>\n'

    return text


def compose_full_message_on_list_of_searches(cur, list_type, user_id, region, region_name):
    """Compose a Final message on the list of searches in the given region"""

    msg = ''

    cur.execute(
        "SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;", (user_id,)
    )

    user_data = cur.fetchone()

    # combine the list of last 20 searches
    if list_type == 'all':

        msg += compose_msg_on_all_last_searches(cur, region)

        if msg:
            msg = 'Последние 20 поисков в разделе <a href="https://lizaalert.org/forum/viewforum.php?f=' + str(region) \
                  + '">' + region_name + '</a>:\n' + msg

        else:
            msg = 'Не получается отобразить последние поиски в разделе ' \
                  '<a href="https://lizaalert.org/forum/viewforum.php?f=' + str(region) \
                  + '">' + region_name + '</a>, что-то пошло не так, простите. Напишите об этом разработчику ' \
                                         'в <a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальном Чате ' \
                                         'в телеграм</a>, пожалуйста.'

    # Combine the list of the latest active searches
    else:

        msg += compose_msg_on_active_searches_in_one_reg(cur, region, user_data)

        if msg:
            msg = 'Актуальные поиски за 60 дней в разделе <a href="https://lizaalert.org/forum/viewforum.php?f=' \
                  + str(region) + '">' + region_name + '</a>:\n' + msg

        else:
            msg = 'В разделе <a href="https://lizaalert.org/forum/viewforum.php?f=' \
                  + str(region) + '">' + region_name + '</a> все поиски за последние 60 дней завершены.'

    return msg


def check_if_new_user(cur, user_id):
    """check if the user is new or not"""

    cur.execute("""SELECT user_id FROM users WHERE user_id=%s LIMIT 1;""", (user_id,))

    info_on_user_from_users = str(cur.fetchone())

    if info_on_user_from_users == 'None':
        user_is_new = True
    else:
        user_is_new = False

    return user_is_new


def check_if_user_has_no_regions(cur, user_id):
    """check if the user has at least one region"""

    cur.execute("""SELECT user_id FROM user_regional_preferences WHERE user_id=%s LIMIT 1;""", (user_id,))

    info_on_user_from_users = str(cur.fetchone())

    if info_on_user_from_users == 'None':
        no_regions = True
    else:
        no_regions = False

    return no_regions


def save_user_pref_role(cur, user_id, role_desc):
    """save user role"""

    role_dict = {'я состою в ЛизаАлерт': 'member',
                 'я хочу помогать ЛизаАлерт': 'new_member',
                 'я ищу человека': 'relative',
                 'у меня другая задача': 'other',
                 'не хочу говорить': 'no_answer'}

    try:
        role = role_dict[role_desc]
    except:  # noqa
        role = 'unidentified'

    cur.execute("""UPDATE users SET role=%s where user_id=%s;""", (role, user_id))

    logging.info(f'[comm]: user {user_id} selected role {role}')

    return role


def save_user_pref_urgency(cur, user_id, urgency_value,
                           b_pref_urgency_highest, b_pref_urgency_high, b_pref_urgency_medium, b_pref_urgency_low):
    """save user urgency"""

    urgency_dict = {b_pref_urgency_highest: {'pref_id': 0, 'pref_name': 'highest'},
                    b_pref_urgency_high: {'pref_id': 1, 'pref_name': 'high'},
                    b_pref_urgency_medium: {'pref_id': 2, 'pref_name': 'medium'},
                    b_pref_urgency_low: {'pref_id': 3, 'pref_name': 'low'}}

    try:
        pref_id = urgency_dict[urgency_value]['pref_id']
        pref_name = urgency_dict[urgency_value]['pref_name']
    except:  # noqa
        pref_id = 99
        pref_name = 'unidentified'

    cur.execute("""DELETE FROM user_pref_urgency WHERE user_id=%s;""", (user_id,))
    cur.execute("""INSERT INTO user_pref_urgency (user_id, pref_id, pref_name, timestamp) VALUES (%s, %s, %s, %s);""",
                (user_id, pref_id, pref_name, datetime.datetime.now()))

    logging.info(f'urgency set as {pref_name} for user_id {user_id}')

    return None


def save_user_coordinates(cur, user_id, input_latitude, input_longitude):
    """Save / update user "home" coordinates"""

    cur.execute(
        "DELETE FROM user_coordinates WHERE user_id=%s;", (user_id,)
    )

    now = datetime.datetime.now()
    cur.execute("""INSERT INTO user_coordinates (user_id, latitude, longitude, upd_time) values (%s, %s, %s, %s);""",
                (user_id, input_latitude, input_longitude, now))

    return None


def show_user_coordinates(cur, user_id):
    """Return the saved user "home" coordinates"""

    cur.execute("""SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;""",
                (user_id,))

    try:
        lat, lon = list(cur.fetchone())
    except:  # noqa
        lat = None
        lon = None

    return lat, lon


def delete_user_coordinates(cur, user_id):
    """Delete the saved user "home" coordinates"""

    cur.execute(
        "DELETE FROM user_coordinates WHERE user_id=%s;", (user_id,)
    )

    return None


def distance_to_search(search_lat, search_lon, user_let, user_lon):
    """Return the distance and direction from user "home" coordinates to the search coordinates"""

    r = 6373.0  # radius of the Earth

    # coordinates in radians
    lat1 = math.radians(float(search_lat))
    lon1 = math.radians(float(search_lon))
    lat2 = math.radians(float(user_let))
    lon2 = math.radians(float(user_lon))

    # change in coordinates
    d_lon = lon2 - lon1

    d_lat = lat2 - lat1

    # Haversine formula
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = r * c
    dist = round(distance)

    # define direction

    def calc_bearing(lat_2, lon_2, lat_1, lon_1):
        d_lon_ = (lon_2 - lon_1)
        x = math.cos(math.radians(lat_2)) * math.sin(math.radians(d_lon_))
        y = math.cos(math.radians(lat_1)) * math.sin(math.radians(lat_2)) - math.sin(math.radians(lat_1)) * math.cos(
            math.radians(lat_2)) * math.cos(math.radians(d_lon_))
        bearing = math.atan2(x, y)
        bearing = math.degrees(bearing)

        return bearing

    def calc_nsew(lat_1, lon_1, lat_2, lon_2):
        # indicators of the direction, like ↖︎
        points = ['&#8593;&#xFE0E;', '&#8599;&#xFE0F;', '&#8594;&#xFE0E;', '&#8600;&#xFE0E;',
                  '&#8595;&#xFE0E;', '&#8601;&#xFE0E;', '&#8592;&#xFE0E;', '&#8598;&#xFE0E;']

        bearing = calc_bearing(lat_1, lon_1, lat_2, lon_2)
        bearing += 22.5
        bearing = bearing % 360
        bearing = int(bearing / 45)  # values 0 to 7
        nsew = points[bearing]

        return nsew

    direction = calc_nsew(lat1, lon1, lat2, lon2)

    return [dist, direction]


def get_user_reg_folders_preferences(cur, user_id):
    """Return user's regional preferences"""

    user_prefs_list = []

    try:
        cur.execute("SELECT forum_folder_num FROM user_regional_preferences WHERE user_id=%s;", (user_id,))
        user_reg_prefs_array = cur.fetchall()

        for line in user_reg_prefs_array:
            user_prefs_list.append(line[0])

        logging.info(str(user_prefs_list))

    except Exception as e:
        logging.info(f'failed to get user regional prefs for user {user_id}')
        logging.exception(e)

    return user_prefs_list


def get_user_role(cur, user_id):
    """Return user's role"""

    user_role = None

    try:
        cur.execute("SELECT role FROM users WHERE user_id=%s LIMIT 1;", (user_id,))
        user_role = cur.fetchone()
        if user_role:
            user_role = user_role[0]

        logging.info(f'user {user_id} role is {user_role}')

    except Exception as e:
        logging.info(f'failed to get user role for user {user_id}')
        logging.exception(e)

    return user_role


def save_preference(cur, user_id, preference):
    """Save user preference on types of notifications to be sent by bot"""

    # the master-table is dict_notif_types:

    pref_dict = {'topic_new': 0,
                 'topic_status_change': 1,
                 'topic_title_change': 2,
                 'topic_comment_new': 3,
                 'topic_inforg_comment_new': 4,
                 'topic_field_trip_new': 5,
                 'topic_field_trip_change': 6,
                 'topic_coords_change': 7,
                 'topic_first_post_change': 8,
                 'bot_news': 20,
                 'all': 30,
                 'not_defined': 99,

                 'new_searches': 0,
                 'status_changes': 1,
                 'title_changes': 2,
                 'comments_changes': 3,
                 'inforg_comments': 4,
                 'field_trips_new': 5,
                 'field_trips_change': 6,
                 'coords_change': 7,
                 'first_post_changes': 8}

    def execute_insert(user, preference_name):
        """execute SQL INSERT command"""

        preference_id = pref_dict[preference_name]
        cur.execute("""INSERT INTO user_preferences 
                        (user_id, preference, pref_id) 
                        VALUES (%s, %s, %s) 
                        ON CONFLICT DO NOTHING;""",
                    (user, preference_name, preference_id))

        return None

    def execute_delete(user, list_of_prefs):
        """execute SQL DELETE command"""

        if list_of_prefs:
            for line in list_of_prefs:
                line_id = pref_dict[line]
                cur.execute("""DELETE FROM user_preferences WHERE user_id=%s AND pref_id=%s;""", (user, line_id))
        else:
            cur.execute("""DELETE FROM user_preferences WHERE user_id=%s;""", (user,))

        return None

    def execute_check(user, pref_list):
        """execute SQL SELECT command and returns TRUE / FALSE if something found"""

        result = False

        for line in pref_list:
            cur.execute("""SELECT id FROM user_preferences WHERE user_id=%s AND preference=%s LIMIT 1;""",
                        (user, line))

            if str(cur.fetchone()) != 'None':
                result = True
                break

        return result

    if preference == 'all':

        execute_delete(user_id, [])
        execute_insert(user_id, preference)

    elif preference in {'new_searches', 'status_changes', 'title_changes', 'comments_changes', 'first_post_changes'}:

        if execute_check(user_id, ['all']):
            execute_insert(user_id, 'bot_news')
        execute_delete(user_id, ['all'])

        execute_insert(user_id, preference)

        if preference == 'comments_changes':
            execute_delete(user_id, ['inforg_comments'])

    elif preference == 'inforg_comments':

        if not execute_check(user_id, ['all', 'comments_changes']):
            execute_insert(user_id, preference)

    elif preference in {'field_trips_new', 'field_trips_change', 'coords_change'}:

        # FIXME – temp deactivation unlit feature will be ready for prod
        # FIXME – to be added to "new_searches" etc group
        # if not execute_check(user_id, ['all']):
        execute_insert(user_id, preference)

    elif preference in {'-new_searches', '-status_changes', '-comments_changes', '-inforg_comments',
                        '-title_changes', '-all', '-field_trips_new', '-field_trips_change', '-coords_change',
                        '-first_post_changes'}:

        if preference == '-all':
            execute_insert(user_id, 'bot_news')
            execute_insert(user_id, 'new_searches')
            execute_insert(user_id, 'status_changes')
            execute_insert(user_id, 'inforg_comments')
            execute_insert(user_id, 'first_post_changes')
        elif preference == '-comments_changes':
            execute_insert(user_id, 'inforg_comments')

        preference = preference[1:]
        execute_delete(user_id, [preference])

    return None


def update_and_download_list_of_regions(cur, user_id, got_message, b_menu_set_region, b_fed_dist_pick_other):
    """Upload, download and compose a message on the list of user's regions"""

    msg = ''
    is_first_entry = None
    region_was_in_db = None
    region_is_the_only = None

    fed_okr_dict = {'Дальневосточный ФО',
                    'Приволжский ФО',
                    'Северо-Кавказский ФО',
                    'Северо-Западный ФО',
                    'Сибирский ФО',
                    'Уральский ФО',
                    'Центральный ФО',
                    'Южный ФО'
                    }

    # upload the new regional setting
    folder_dict = {'Москва и МО: Активные Поиски': [276],
                   'Москва и МО: Инфо Поддержка': [41],

                   'Белгородская обл.': [236],
                   'Брянская обл.': [138],
                   'Владимирская обл.': [123, 233],
                   'Воронежская обл.': [271, 315],
                   'Ивановская обл.': [132, 193],
                   'Калужская обл.': [185],
                   'Костромская обл.': [151],
                   'Курская обл.': [186],
                   'Липецкая обл.': [272],
                   'Орловская обл.': [222, 324],
                   'Рязанская обл.': [155],
                   'Смоленская обл.': [122],
                   'Тамбовская обл.': [273],
                   'Тверская обл.': [126],
                   'Тульская обл.': [125],
                   'Ярославская обл.': [264],
                   'Прочие поиски по ЦФО': [179],

                   'Адыгея': [299],
                   'Астраханская обл.': [336],
                   'Волгоградская обл.': [131],
                   'Краснодарский край': [162],
                   'Крым': [293],
                   'Ростовская обл.': [157],
                   'Прочие поиски по ЮФО': [180],

                   'Архангельская обл.': [330],
                   'Вологодская обл.': [370, 369, 368, 367],
                   'Карелия': [403, 404],
                   'Коми': [378, 377, 376],
                   'Ленинградская обл.': [120, 300],
                   'Мурманская обл.': [214, 371, 372, 373],
                   'Псковская обл.': [210, 383, 382],
                   'Прочие поиски по СЗФО': [181],

                   'Амурская обл.': [390],
                   'Бурятия': [274],
                   'Приморский край': [298],
                   'Хабаровский край': [154],
                   'Прочие поиски по ДФО': [188],

                   'Алтайский край': [161],
                   'Иркутская обл.': [137, 387, 386, 303],
                   'Кемеровская обл.': [202, 308],
                   'Красноярский край': [269, 318],
                   'Новосибирская обл.': [177, 310],
                   'Омская обл.': [153, 314],
                   'Томская обл.': [215, 401],
                   'Хакасия': [402],
                   'Прочие поиски по СФО': [182],

                   'Свердловская обл.': [213],
                   'Курганская обл.': [391, 392],
                   'Тюменская обл.': [339],
                   'Ханты-Мансийский АО': [338],
                   'Челябинская обл.': [280],
                   'Ямало-Ненецкий АО': [204],
                   'Прочие поиски по УФО': [187],

                   'Башкортостан': [191, 235],
                   'Кировская обл.': [211, 275],
                   'Марий Эл': [295, 297],
                   'Мордовия': [294],
                   'Нижегородская обл.': [121, 289],
                   'Оренбургская обл.': [337],
                   'Пензенская обл.': [170, 322],
                   'Пермский край': [143, 325],
                   'Самарская обл.': [333, 334, 305],
                   'Саратовская обл.': [212],
                   'Татарстан': [163, 231],
                   'Удмуртия': [237, 239],
                   'Ульяновская обл.': [290, 320],
                   'Чувашия': [265, 327],
                   'Прочие поиски по ПФО': [183],

                   'Дагестан': [292],
                   'Ставропольский край': [173],
                   'Чечня': [291],
                   'Кабардино-Балкария': [301],
                   'Ингушетия': [422],
                   'Северная Осетия': [423],
                   'Прочие поиски по СКФО': [184],

                   'Прочие поиски по РФ': [116]
                   }

    # Reversed dict is needed on the last step
    rev_reg_dict = {value[0]: key for (key, value) in folder_dict.items()}

    # TODO - get the list of regions from PSQL
    # TODO ^^^

    # case for the first entry to the screen of Reg Settings
    if got_message == b_menu_set_region:
        is_first_entry = 'yes'
    elif got_message in fed_okr_dict or got_message == b_fed_dist_pick_other:
        pass
    else:
        try:

            list_of_regs_to_upload = folder_dict[got_message]

            # any region
            cur.execute(
                """SELECT forum_folder_num from user_regional_preferences WHERE user_id=%s;""", (user_id,)
            )

            user_curr_regs_temp = cur.fetchall()
            user_curr_regs = [reg[0] for reg in user_curr_regs_temp]

            for user_reg in user_curr_regs:
                if list_of_regs_to_upload[0] == user_reg:
                    region_was_in_db = 'yes'
                    break
            if region_was_in_db:
                if len(user_curr_regs) - len(list_of_regs_to_upload) < 1:
                    region_is_the_only = 'yes'

            # Scenario: this setting WAS in place, and now we need to DELETE it
            if region_was_in_db == 'yes' and not region_is_the_only:
                for region in list_of_regs_to_upload:
                    cur.execute(
                        """DELETE FROM user_regional_preferences WHERE user_id=%s and forum_folder_num=%s;""",
                        (user_id, region)
                    )

            # Scenario: this setting WAS in place, but now it's the last one - we cannot delete it
            elif region_was_in_db == 'yes' and region_is_the_only:
                pass

            # Scenario: it's a NEW setting, we need to ADD it
            else:
                for region in list_of_regs_to_upload:
                    cur.execute(
                        """INSERT INTO user_regional_preferences (user_id, forum_folder_num) values (%s, %s);""",
                        (user_id, region)
                    )

        except Exception as e:
            logging.info('failed to upload & download the list of user\'s regions')
            logging.exception(e)

    # Get the list of resulting regions
    cur.execute(
        """SELECT forum_folder_num from user_regional_preferences WHERE user_id=%s;""", (user_id,)
    )

    user_curr_regs = cur.fetchall()
    user_curr_regs_list = [reg[0] for reg in user_curr_regs]

    for reg in user_curr_regs_list:
        if reg in rev_reg_dict:
            msg += ',\n &#8226; ' + rev_reg_dict[reg]

    msg = msg[1:]

    if is_first_entry:
        pre_msg = "Бот может показывать поиски в любом регионе работы ЛА.\n"
        pre_msg += "Вы можете подписаться на несколько регионов – просто кликните на соответствующие кнопки регионов." \
                   "\nЧтобы ОТПИСАТЬСЯ от ненужных регионов – нажмите на соответствующую кнопку региона еще раз.\n\n"
        pre_msg += "Текущий список ваших регионов:"
        msg = pre_msg + msg
    elif region_is_the_only:
        msg = 'Ваш регион поисков настроен' + msg + '\n\nВы можете продолжить добавлять регионы, либо нажмите ' \
                                                    'кнопку "в начало", чтобы продолжить работу с ботом.'
    elif got_message in fed_okr_dict or got_message == b_fed_dist_pick_other:
        if user_curr_regs_list:
            msg = 'Текущий список ваших регионов:' + msg
        else:
            msg = 'Пока список выбранных регионов пуст. Выберите хотя бы один.'
    else:
        msg = 'Записали. Обновленный список ваших регионов:' + msg + '\n\nВы можете продолжить добавлять регионы, ' \
                                                                     'либо нажмите кнопку "в начало", чтобы ' \
                                                                     'продолжить работу с ботом.'

    return msg


def get_last_bot_msg(cur, user_id):
    """Get the last bot message to user to define if user is expected to give exact answer"""

    cur.execute(
        """
        SELECT msg_type FROM msg_from_bot WHERE user_id=%s LIMIT 1;
        """, (user_id,))

    extract = cur.fetchone()
    logging.info(f'get the last bot message to user to define if user is expected to give exact answer')
    logging.info(str(extract))

    if extract and extract != 'None':
        msg_type = extract[0]
    else:
        msg_type = None

    if msg_type:
        logging.info(f'before this message bot was waiting for {msg_type} from user {user_id}')
    else:
        logging.info(f'before this message bot was NOT waiting anything from user {user_id}')

    return msg_type


def generate_yandex_maps_place_link(lat, lon, param):
    """Compose a link to yandex map with the given coordinates"""

    coordinates_format = "{0:.5f}"

    if param == 'coords':
        display = str(coordinates_format.format(float(lat))) + ', ' + str(coordinates_format.format(float(lon)))
    else:
        display = 'Карта'

    msg = f'<a href="https://yandex.ru/maps/?pt={lon},{lat}&z=11&l=map">{display}</a>'

    return msg


def get_param_if_exists(upd, func_input):
    """Return either value if exist or None. Used for messages with changing schema from telegram"""

    update = upd  # noqa

    try:
        func_output = eval(func_input)
    except:  # noqa
        func_output = None

    return func_output


def manage_age(cur, user_id, user_input):
    """Save user Age preference and generate the list of updated Are preferences"""

    class AgePeriod:

        def __init__(self,
                     description=None,
                     name=None,
                     current=None,
                     min_age=None,
                     max_age=None,
                     order=None
                     ):
            self.desc = description
            self.name = name
            self.now = current
            self.min = min_age
            self.max = max_age
            self.order = order

    age_list = [AgePeriod(description='Маленькие Дети 0-6 лет', name='0-6', min_age=0, max_age=6, order=0),
                AgePeriod(description='Подростки 7-13 лет', name='7-13', min_age=7, max_age=13, order=1),
                AgePeriod(description='Молодежь 14-20 лет', name='14-20', min_age=14, max_age=20, order=2),
                AgePeriod(description='Взрослые 21-50 лет', name='21-50', min_age=21, max_age=50, order=3),
                AgePeriod(description='Старшее Поколение 51-80 лет', name='51-80', min_age=51, max_age=80, order=4),
                AgePeriod(description='Старцы более 80 лет', name='80-on', min_age=80, max_age=120, order=5)]

    if user_input:
        user_want_activate = True if re.search(r'(?i)включить', user_input) else False
        user_new_setting = re.sub(r'.*чить: ', '', user_input)

        chosen_setting = None
        for line in age_list:
            if user_new_setting == line.desc:
                chosen_setting = line
                break

        if user_want_activate:
            cur.execute("""INSERT INTO user_pref_age (user_id, period_name, period_set_date, period_min, period_max) 
                        values (%s, %s, %s, %s, %s) ON CONFLICT (user_id, period_min, period_max) DO NOTHING;""",
                        (user_id, chosen_setting.name, datetime.datetime.now(), chosen_setting.min, chosen_setting.max))
        else:
            cur.execute(
                """DELETE FROM user_pref_age WHERE user_id=%s AND period_min=%s AND period_max=%s;""",
                (user_id, chosen_setting.min, chosen_setting.max))

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
            cur.execute("""INSERT INTO user_pref_age (user_id, period_name, period_set_date, period_min, period_max) 
                        values (%s, %s, %s, %s, %s) ON CONFLICT (user_id, period_min, period_max) DO NOTHING;""",
                        (user_id, line.name, datetime.datetime.now(), line.min, line.max))

    list_of_buttons = []
    for line in age_list:
        if line.now:
            list_of_buttons.append([f'отключить: {line.desc}'])
        else:
            list_of_buttons.append([f'включить: {line.desc}'])

    return list_of_buttons, first_visit


def save_user_pref_topic_type(cur, user_id, pref_id, user_role):
    def save(pref_type_id):
        cur.execute("""INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp) 
                                            values (%s, %s, %s) ON CONFLICT (user_id, topic_type_id) DO NOTHING;""",
                    (user_id, pref_type_id, datetime.datetime.now()))
        return None

    if not (cur and user_id and pref_id):
        return None

    if pref_id == 'default':
        if user_role in {'member', 'new_member'}:
            default_topic_type_id = [0, 3, 4, 5]  # 0=regular, 3=training, 4=info_support, 5=resonance
        else:
            default_topic_type_id = [0, 4, 5]  # 0=regular, 4=info_support, 5=resonance

        for type_id in default_topic_type_id:
            save(type_id)

    else:
        save(pref_id)

    return None


def manage_radius(cur, user_id, user_input, b_menu, b_act, b_deact, b_change, b_back, b_home_coord, expect_before):
    """Save user Radius preference and generate the actual radius preference"""

    def check_saved_radius(user):
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
                bot_message = f'Сейчас вами установлено ограничение радиуса {saved_radius} км. ' \
                              f'Вы в любой момент можете изменить или снять это ограничение.\n\n' \
                              'ВАЖНО! Вы всё равно будете проинформированы по всем поискам, по которым ' \
                              'Бот не смог распознать никакие координаты.\n\n' \
                              'Также, бот в первую очередь ' \
                              'проверяет расстояние от штаба, а если он не указан, то до ближайшего ' \
                              'населенного пункта (или топонима), указанного в теме поиска. ' \
                              'Расстояние считается по прямой.'
            else:
                list_of_buttons = [[b_act], [b_home_coord], [b_back]]
                bot_message = 'Данная настройка позволяет вам ограничить уведомления от бота только теми поисками, ' \
                              'для которых расстояние от ваших "домашних координат" до штаба/города ' \
                              'не превышает указанного вами Радиуса.\n\n' \
                              'ВАЖНО! Вы всё равно будете проинформированы по всем поискам, по которым ' \
                              'Бот не смог распознать никакие координаты.\n\n' \
                              'Также, Бот в первую очередь ' \
                              'проверяет расстояние от штаба, а если он не указан, то до ближайшего ' \
                              'населенного пункта (или топонима), указанного в теме поиска. ' \
                              'Расстояние считается по прямой.'

        elif user_input in {b_act, b_change}:
            expect_after = 'radius_input'
            reply_markup_needed = False
            saved_radius = check_saved_radius(user_id)
            if saved_radius:
                bot_message = f'У вас установлено максимальное расстояние до поиска {saved_radius}.' \
                              f'\n\nВведите обновлённое расстояние в километрах по прямой в формате простого ' \
                              f'числа (например: 150) и нажмите обычную кнопку отправки сообщения'
            else:
                bot_message = 'Введите расстояние в километрах по прямой в формате простого числа ' \
                              '(например: 150) и нажмите обычную кнопку отправки сообщения'

        elif user_input == b_deact:
            list_of_buttons = [[b_act], [b_menu], [b_back]]
            cur.execute("""DELETE FROM user_pref_radius WHERE user_id=%s;""", (user_id,))
            bot_message = 'Ограничение на расстояние по поискам снято!'

        elif expect_before == 'radius_input':
            number = re.search(r'[0-9]{1,6}', str(user_input))
            if number:
                number = int(number.group())
            if number and number > 0:
                cur.execute("""INSERT INTO user_pref_radius (user_id, radius) 
                               VALUES (%s, %s) ON CONFLICT (user_id) DO
                               UPDATE SET radius=%s;""", (user_id, number, number))
                saved_radius = check_saved_radius(user_id)
                bot_message = f'Сохранили! Теперь поиски, у которых расстояние до штаба, ' \
                              f'либо до ближайшего населенного пункта (топонима) превосходит ' \
                              f'{saved_radius} км по прямой, не будут вас больше беспокоить. ' \
                              f'Настройку можно изменить в любое время.'
                list_of_buttons = [[b_change], [b_deact], [b_menu], [b_back]]
            else:
                bot_message = 'Не могу разобрать цифры. Давайте еще раз попробуем?'
                list_of_buttons = [[b_act], [b_menu], [b_back]]

    if reply_markup_needed:
        reply_markup = ReplyKeyboardMarkup(list_of_buttons, resize_keyboard=True)
    else:
        reply_markup = ReplyKeyboardRemove()

    return bot_message, reply_markup, expect_after


# FIXME – 27.11.2023 – to be deleted when manage_topic_type_inline will work
def manage_topic_type(cur, user_id, user_input, b) -> Union[tuple[None, None], tuple[str, ReplyKeyboardMarkup]]:
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

        cur.execute("""INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp) 
                        VALUES (%s, %s, %s) ON CONFLICT (user_id, topic_type_id) DO NOTHING;""",
                    (user, type_id, datetime.datetime.now()))
        return None

    if not user_input:
        return None, None

    list_of_current_setting_ids = check_saved_topic_types(user_id)

    if user_input == b.set.topic_type.text:

        bot_message = 'Вы можете выбрать, по каким типам поисков или мероприятий бот должен присылать ' \
                      'вам уведомления. На данный моменты вы можете выбрать следующие виды поисков или ' \
                      'мероприятий. Вы можете выбрать несколько значений. Выбор можно изменить в любой момент.'
        list_of_ids_to_change_now = []
    else:
        topic_id = b.topic_types.button_by_text(user_input).id
        list_of_ids_to_change_now = [topic_id]
        user_wants_to_enable = if_user_enables(user_input)
        if user_wants_to_enable is None:
            bot_message = ''
            pass
        elif user_wants_to_enable == True:  # noqa. not a poor design – function can be: None, True, False
            bot_message = f'Супер, мы включили уведомления по таким типам поисков / мероприятиям'
            record_topic_type(user_id, topic_id)
        else: # user_wants_to_enable == False:  # noqa. not a poor design – function can be: None, True, False
            if len(list_of_current_setting_ids) == 1:
                bot_message = 'Изменения не внесены. У вас должен быть включен хотя бы один тип поиска или мероприятия.'
            else:
                bot_message = f'Хорошо, мы изменили список настроек'
                delete_topic_type(user_id, topic_id)

    keyboard = b.topic_types.keyboard(act_list=list_of_current_setting_ids, change_list=list_of_ids_to_change_now)
    keyboard += [[b.core.to_start.text]]
    reply_markup = InlineKeyboardMarkup(keyboard, resize_keyboard=True)

    logging.info(f'{list_of_current_setting_ids=}')
    logging.info(f'{user_input=}')
    logging.info(f'{list_of_ids_to_change_now=}')
    logging.info(f'{keyboard=}')

    return bot_message, reply_markup
# FIXME ^^^


def manage_topic_type_inline(cur, user_id, user_input, b) -> Union[tuple[None, None], tuple[str, ReplyKeyboardMarkup]]:
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

        cur.execute("""INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp) 
                        VALUES (%s, %s, %s) ON CONFLICT (user_id, topic_type_id) DO NOTHING;""",
                    (user, type_id, datetime.datetime.now()))
        return None

    if not user_input:
        return None, None

    list_of_current_setting_ids = check_saved_topic_types(user_id)

    if user_input == b.set.topic_type.text:

        bot_message = 'Вы можете выбрать, по каким типам поисков или мероприятий бот должен присылать ' \
                      'вам уведомления. На данный моменты вы можете выбрать следующие виды поисков или ' \
                      'мероприятий. Вы можете выбрать несколько значений. Выбор можно изменить в любой момент.'
        list_of_ids_to_change_now = []
    else:
        topic_id = b.topic_types.button_by_text(user_input).id
        list_of_ids_to_change_now = [topic_id]
        user_wants_to_enable = if_user_enables(user_input)
        if user_wants_to_enable is None:
            bot_message = ''
            pass
        elif user_wants_to_enable == True:  # noqa. not a poor design – function can be: None, True, False
            bot_message = f'Супер, мы включили уведомления по таким типам поисков / мероприятиям'
            record_topic_type(user_id, topic_id)
        else: # user_wants_to_enable == False:  # noqa. not a poor design – function can be: None, True, False
            if len(list_of_current_setting_ids) == 1:
                bot_message = 'Изменения не внесены. У вас должен быть включен хотя бы один тип поиска или мероприятия.'
            else:
                bot_message = f'Хорошо, мы изменили список настроек'
                delete_topic_type(user_id, topic_id)

    keyboard = b.topic_types.keyboard(act_list=list_of_current_setting_ids, change_list=list_of_ids_to_change_now)
    keyboard += [[{"text": "в начало", "callback_data": "в начало"}]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logging.info(f'{list_of_current_setting_ids=}')
    logging.info(f'{user_input=}')
    logging.info(f'{list_of_ids_to_change_now=}')
    logging.info(f'{keyboard=}')

    return bot_message, reply_markup


def manage_if_moscow(cur, user_id, username, got_message, b_reg_moscow, b_reg_not_moscow,
                     reply_markup, keyboard_fed_dist_set, bot_message, user_role):
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
                (user_id, 276))
            cur.execute(
                """INSERT INTO user_regional_preferences (user_id, forum_folder_num) values
                (%s, %s);""",
                (user_id, 41))
            cur.execute(
                """INSERT INTO user_pref_region (user_id, region_id) values
                (%s, %s);""",
                (user_id, 1))

    # if region is NOT Moscow
    elif got_message == b_reg_not_moscow:

        save_onboarding_step(user_id, username, 'moscow_replied')

        bot_message = 'Спасибо, тогда для корректной работы Бота, пожалуйста, выберите свой регион: ' \
                      'сначала обозначьте Федеральный Округ, ' \
                      'а затем хотя бы один Регион поисков, чтобы отслеживать поиски в этом регионе. ' \
                      'Вы в любой момент сможете изменить ' \
                      'список регионов через настройки бота.'
        reply_markup = ReplyKeyboardMarkup(keyboard_fed_dist_set, resize_keyboard=True)

    else:
        bot_message = None
        reply_markup = None

    return bot_message, reply_markup


def manage_linking_to_forum(cur, got_message, user_id, b_set_forum_nick, b_back_to_start,
                            bot_request_bfr_usr_msg, b_admin_menu, b_test_menu, b_yes_its_me, b_no_its_not_me,
                            b_settings, reply_markup_main):
    """manage all interactions re connection of telegram and forum user accounts"""

    bot_message, reply_markup, bot_request_aft_usr_msg = None, None, None

    if got_message == b_set_forum_nick:

        # TODO: if user_is linked to forum so
        cur.execute("""SELECT forum_username, forum_user_id 
                       FROM user_forum_attributes 
                       WHERE status='verified' AND user_id=%s 
                       ORDER BY timestamp DESC 
                       LIMIT 1;""",
                    (user_id,))
        saved_forum_user = cur.fetchone()

        if not saved_forum_user:

            bot_message = 'Бот сможет быть еще полезнее, эффективнее и быстрее, если указать ваш аккаунт на форуме ' \
                          'lizaalert.org\n\n' \
                          'Для этого просто введите ответным сообщением своё имя пользователя (логин).\n\n' \
                          'Если возникнут ошибки при распознавании – просто скопируйте имя с форума и ' \
                          'отправьте боту ответным сообщением.'
            keyboard = [[b_back_to_start]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            bot_request_aft_usr_msg = 'input_of_forum_username'

        else:

            saved_forum_username, saved_forum_user_id = list(saved_forum_user)

            bot_message = f'Ваш телеграм уже привязан к аккаунту ' \
                          f'<a href="https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u=' \
                          f'{saved_forum_user_id}">{saved_forum_username}</a> ' \
                          f'на форуме ЛизаАлерт. Больше никаких действий касательно аккаунта на форуме не требуется:)'
            keyboard = [[b_settings], [b_back_to_start]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    elif bot_request_bfr_usr_msg == 'input_of_forum_username' and \
            got_message not in {b_admin_menu, b_back_to_start, b_test_menu} and len(got_message.split()) < 4:
        message_for_pubsub = [user_id, got_message]
        publish_to_pubsub('parse_user_profile_from_forum', message_for_pubsub)
        bot_message = 'Сейчас посмотрю, это может занять до 10 секунд...'
        keyboard = [[b_back_to_start]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    elif got_message in {b_yes_its_me}:

        # Write "verified" for user
        cur.execute("""UPDATE user_forum_attributes SET status='verified'
                WHERE user_id=%s and timestamp =
                (SELECT MAX(timestamp) FROM user_forum_attributes WHERE user_id=%s);""",
                    (user_id, user_id))

        bot_message = 'Отлично, мы записали: теперь бот будет понимать, кто вы на форуме.\nЭто поможет ' \
                      'вам более оперативно получать сообщения о поисках, по которым вы оставляли ' \
                      'комментарии на форуме.'
        keyboard = [[b_settings], [b_back_to_start]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    elif got_message == b_no_its_not_me:
        bot_message = 'Пожалуйста, тщательно проверьте написание вашего ника на форуме ' \
                      '(кириллица/латиница, без пробела в конце) и введите его заново'
        keyboard = [[b_set_forum_nick], [b_back_to_start]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        bot_request_aft_usr_msg = 'input_of_forum_username'

    elif got_message == b_back_to_start:
        bot_message = 'возвращаемся в главное меню'
        reply_markup = reply_markup_main

    return bot_message, reply_markup, bot_request_aft_usr_msg


def save_onboarding_step(user_id, username, step):
    """save the certain step in onboarding"""

    # to avoid eval errors in recipient script
    if not username:
        username = 'unknown'

    message_for_pubsub = {'action': 'update_onboarding',
                          'info': {'user': user_id, 'username': username},
                          'time': str(datetime.datetime.now()),
                          'step': step}
    publish_to_pubsub('topic_for_user_management', message_for_pubsub)

    return None


def check_onboarding_step(cur, user_id, user_is_new):
    """checks the latest step of onboarding"""

    if user_is_new:
        return 0, 'start'

    try:
        cur.execute("""SELECT step_id, step_name, timestamp FROM user_onboarding 
                               WHERE user_id=%s ORDER BY step_id DESC;""",
                    (user_id,))
        raw_data = cur.fetchone()
        if raw_data:
            step_id, step_name, time = list(raw_data)
        else:
            step_id, step_name = 99, None

    except Exception as e:
        logging.exception(e)
        step_id, step_name = 99, None

    return step_id, step_name


async def leave_chat_async(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.leave_chat(chat_id=context.job.chat_id)

    return None


async def prepare_message_for_leave_chat_async(user_id):
    bot_token = get_secrets("bot_api_token__prod")
    application = Application.builder().token(bot_token).build()
    job_queue = application.job_queue
    job = job_queue.run_once(leave_chat_async, 0, chat_id=user_id)

    async with application:
        await application.initialize()
        await application.start()
        await application.stop()
        await application.shutdown()

    return 'ok'


def process_leaving_chat_async(user_id) -> None:
    asyncio.run(prepare_message_for_leave_chat_async(user_id))

    return None


async def send_message_async(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=context.job.chat_id, **context.job.data)

    return None


async def prepare_message_for_async(user_id, data):
    bot_token = get_secrets("bot_api_token__prod")
    application = Application.builder().token(bot_token).build()
    job_queue = application.job_queue
    job = job_queue.run_once(send_message_async, 0, data=data, chat_id=user_id)

    async with application:
        await application.initialize()
        await application.start()
        await application.stop()
        await application.shutdown()

    return 'ok'


def process_sending_message_async(user_id, data) -> None:
    asyncio.run(prepare_message_for_async(user_id, data))

    return None


def process_response_of_api_call(user_id, response):
    """process response received as a result of Telegram API call while sending message/location"""

    try:
        if response.ok:
            logging.info(f'message to {user_id} was successfully sent')
            return 'completed'

        elif response.status_code == 400:  # Bad Request
            logging.info(f'Bad Request: message to {user_id} was not sent, {response.reason=}')
            logging.exception('BAD REQUEST')
            return 'cancelled_bad_request'

        elif response.status_code == 403:  # FORBIDDEN
            logging.info(f'Forbidden: message to {user_id} was not sent, {response.reason=}')
            action = None
            if response.text.find('bot was blocked by the user') != -1:
                action = 'block_user'
            if response.text.find('user is deactivated') != -1:
                action = 'delete_user'
            if action:
                message_for_pubsub = {'action': action, 'info': {'user': user_id}}
                publish_to_pubsub('topic_for_user_management', message_for_pubsub)
                logging.info(f'Identified user id {user_id} to do {action}')
            return 'cancelled'

        elif 420 <= response.status_code <= 429:  # 'Flood Control':
            logging.info(f'Flood Control: message to {user_id} was not sent, {response.reason=}')
            logging.exception('FLOOD CONTROL')
            return 'failed_flood_control'

        else:
            logging.info(f'UNKNOWN ERROR: message to {user_id} was not sent, {response.reason=}')
            logging.exception('UNKNOWN ERROR')
            return 'cancelled'

    except Exception as e:
        logging.info(f'Response is corrupted')
        logging.exception(e)
        return 'failed'


def send_message_to_api(bot_token, user_id, message, params):
    """send message directly to Telegram API w/o any wrappers ar libraries"""

    try:
        parse_mode = ''
        disable_web_page_preview = ''
        reply_markup = ''
        if params:
            if 'parse_mode' in params.keys():
                parse_mode = f'&parse_mode={params["parse_mode"]}'
            if 'disable_web_page_preview' in params.keys():
                disable_web_page_preview = f'&disable_web_page_preview={params["disable_web_page_preview"]}'
            if 'reply_markup' in params.keys():
                rep_as_str = str(json.dumps(params['reply_markup']))
                reply_markup = f'&reply_markup={urllib.parse.quote(rep_as_str)}'
        message_encoded = f'&text={urllib.parse.quote(message)}'

        request_text = f'https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={user_id}' \
                       f'{message_encoded}{parse_mode}{disable_web_page_preview}{reply_markup}'

        with requests.Session() as session:
            response = session.get(request_text)
            notify_admin(str(response))

    except Exception as e:
        logging.exception(e)
        logging.info(f'Error in getting response from Telegram')
        response = None

    result = process_response_of_api_call(user_id, response)

    return result


def get_the_update(bot, request):
    """converts a request to an update"""

    try:
        update = Update.de_json(request.get_json(force=True), bot)
    except Exception as e:
        logging.exception(e)
        logging.error('request received has no update')
        update = None

    logging.info(f'update received: {request.get_json(force=True)}')

    return update


def get_basic_update_parameters(update):
    """de-fragment update to the key parameters"""

    user_new_status = get_param_if_exists(update, 'update.my_chat_member.new_chat_member.status')
    timer_changed = get_param_if_exists(update, 'update.message.message_auto_delete_timer_changed')
    photo = get_param_if_exists(update, 'update.message.photo')
    document = get_param_if_exists(update, 'update.message.document')
    voice = get_param_if_exists(update, 'update.message.voice')
    contact = get_param_if_exists(update, 'update.message.contact')
    inline_query = get_param_if_exists(update, 'update.inline_query')
    sticker = get_param_if_exists(update, 'update.message.sticker.file_id')
    user_latitude = get_param_if_exists(update, 'update.effective_message.location.latitude')
    user_longitude = get_param_if_exists(update, 'update.effective_message.location.longitude')
    got_message = get_param_if_exists(update, 'update.effective_message.text')

    channel_type = get_param_if_exists(update, 'update.edited_channel_post.chat.type')
    if not channel_type:
        channel_type = get_param_if_exists(update, 'update.channel_post.chat.type')
    if not channel_type:
        channel_type = get_param_if_exists(update, 'update.my_chat_member.chat.type')

    # the purpose of this bot - sending messages to unique users, this way
    # chat_id is treated as user_id and vice versa (which is not true in general)

    username = get_param_if_exists(update, 'update.effective_user.username')

    if not username:
        username = get_param_if_exists(update, 'update.effective_message.from_user.username')
        if username:
            logging.exception(f'EFFECTIVE_USER.USERNAME IS NOT GIVEN! BUT WE\'VE GOT IT FROM EFF_MESSAGE!')

    user_id = get_param_if_exists(update, 'update.effective_user.id')
    if not user_id:
        logging.exception(f'EFFECTIVE USER.ID IS NOT GIVEN!')
        user_id = get_param_if_exists(update, 'update.effective_message.from_user.id')
    if not user_id:
        user_id = get_param_if_exists(update, 'update.effective_message.chat.id')
    if not user_id:
        user_id = get_param_if_exists(update, 'update.edited_channel_post.chat.id')
    if not user_id:
        user_id = get_param_if_exists(update, 'update.my_chat_member.chat.id')
    if not user_id:
        user_id = get_param_if_exists(update, 'update.inline_query.from.id')
    if not user_id:
        logging.info('failed to define user_id')

    # FIXME – 17.11.2023 – playing with getting inline buttons interactions
    my_list = [user_new_status, timer_changed, photo, document, voice, contact, inline_query, sticker,
               user_latitude, user_longitude, got_message, channel_type, username, user_id]
    callback_query = get_param_if_exists(update, 'update.callback_query')
    # notify_admin(f'initial set of attrs: {my_list}')
    if callback_query:
        notify_admin(f'{callback_query=}')
        callback_data = callback_query.data
        notify_admin(f'{callback_data=}')
        try:
            callback_data = eval(callback_data)
            notify_admin(f'{callback_data=}')
        except Exception as e:
            logging.exception(e)
            notify_admin(f'callback dict was not recognized for {callback_data=}')

    # FIXME ^^^

    return user_new_status, timer_changed, photo, document, voice, contact, inline_query, \
           sticker, user_latitude, user_longitude, got_message, channel_type, username, user_id


def save_new_user(user_id, username):
    """send pubsub message to dedicated script to save new user"""

    username = username if username else 'unknown'
    message_for_pubsub = {'action': 'new', 'info': {'user': user_id, 'username': username},
                          'time': str(datetime.datetime.now())}
    publish_to_pubsub('topic_for_user_management', message_for_pubsub)

    return None


def process_unneeded_messages(update, user_id, timer_changed, photo, document, voice, sticker, channel_type,
                              contact, inline_query):
    """process messages which are not a part of designed dialogue"""

    # CASE 2 – when user changed auto-delete setting in the bot
    if timer_changed:
        logging.info('user changed auto-delete timer settings')

    # CASE 3 – when user sends a PHOTO or attached DOCUMENT or VOICE message
    elif photo or document or voice or sticker:
        logging.debug('user sends photos to bot')

        bot_message = 'Спасибо, интересное! Однако, бот работает только с текстовыми командами. ' \
                      'Пожалуйста, воспользуйтесь текстовыми кнопками бота, находящимися на ' \
                      'месте обычной клавиатуры телеграм.'
        data = {'text': bot_message}
        process_sending_message_async(user_id=user_id, data=data)

    # CASE 4 – when some Channel writes to bot
    elif channel_type and user_id < 0:
        notify_admin('[comm]: INFO: CHANNEL sends messages to bot!')

        try:
            process_leaving_chat_async(user_id)
            notify_admin(f'[comm]: INFO: we have left the CHANNEL {user_id}')

        except Exception as e:
            logging.info(f'[comm]: Leaving channel was not successful: {user_id}')
            logging.exception(e)
            notify_admin(f'[comm]: Leaving channel was not successful: {user_id}')

    # CASE 5 – when user sends Contact
    elif contact:

        bot_message = 'Спасибо, буду знать. Вот только бот не работает с контактами и отвечает ' \
                      'только на определенные текстовые команды.'
        data = {'text': bot_message}
        process_sending_message_async(user_id=user_id, data=data)

    # CASE 6 – when user mentions bot as @LizaAlert_Searcher_Bot in another telegram chat. Bot should do nothing
    elif inline_query:
        notify_admin('[comm]: User mentioned bot in some chats')
        logging.info(f'bot was mentioned in other chats: {update}')

    return None


def process_block_unblock_user(user_id, user_new_status):
    """processing of system message on user action to block/unblock the bot"""

    try:
        status_dict = {'kicked': 'block_user', 'member': 'unblock_user'}

        # mark user as blocked / unblocked in psql
        message_for_pubsub = {'action': status_dict[user_new_status], 'info': {'user': user_id}}
        publish_to_pubsub('topic_for_user_management', message_for_pubsub)

        if user_new_status == 'member':
            bot_message = 'С возвращением! Бот скучал:) Жаль, что вы долго не заходили. ' \
                          'Мы постарались сохранить все ваши настройки с вашего прошлого визита. ' \
                          'Если у вас есть трудности в работе бота или пожелания, как сделать бот ' \
                          'удобнее – напишите, пожалуйста, свои мысли в' \
                          '<a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальный Чат' \
                          'в телеграм</a>. Спасибо:)'

            keyboard_main = [['посмотреть актуальные поиски'], ['настроить бот'], ['другие возможности']]
            reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)

            data = {'text': bot_message, 'reply_markup': reply_markup,
                    'parse_mode': 'HTML', 'disable_web_page_preview': True}
            process_sending_message_async(user_id=user_id, data=data)

    except Exception as e:
        logging.info('Error in finding basic data for block/unblock user in Communicate script')
        logging.exception(e)

    return None


def save_bot_reply_to_user(cur, user_id, bot_message):
    """save bot's reply to user in psql"""

    if len(bot_message) > 27 and bot_message[28] in {'Актуальные поиски за 60 дней', 'Последние 20 поисков в разде'}:
        bot_message = bot_message[28]

    cur.execute("""INSERT INTO dialogs (user_id, author, timestamp, message_text) values (%s, %s, %s, %s);""",
                (user_id, 'bot', datetime.datetime.now(), bot_message))

    return None


def save_user_message_to_bot(cur, user_id, got_message):
    """save user's message to bot in psql"""

    cur.execute("""INSERT INTO dialogs (user_id, author, timestamp, message_text) values (%s, %s, %s, %s);""",
                (user_id, 'user', datetime.datetime.now(), got_message))

    return None


def get_coordinates_from_string(got_message, lat_placeholder, lon_placeholder):
    """gets coordinates from string"""

    user_latitude, user_longitude = None, None
    # Check if user input is in format of coordinates
    # noinspection PyBroadException
    try:
        numbers = [float(s) for s in re.findall(r'-?\d+\.?\d*', got_message)]
        if numbers and len(numbers) > 1 and 30 < numbers[0] < 80 and 10 < numbers[1] < 190:
            user_latitude = numbers[0]
            user_longitude = numbers[1]
    except Exception as e:
        logging.info(f'manual coordinates were not identified from string {got_message}')

    if not (user_latitude and user_longitude):
        user_latitude = lat_placeholder
        user_longitude = lon_placeholder

    return user_latitude, user_longitude


def process_user_coordinates(cur, user_id, user_latitude, user_longitude, b_coords_check, b_coords_del, b_back_to_start,
                             bot_request_aft_usr_msg):
    """process coordinates which user sent to bot"""

    save_user_coordinates(cur, user_id, user_latitude, user_longitude)

    bot_message = 'Ваши "домашние координаты" сохранены:\n'
    bot_message += generate_yandex_maps_place_link(user_latitude, user_longitude, 'coords')
    bot_message += '\nТеперь для всех поисков, где удастся распознать координаты штаба или ' \
                   'населенного пункта, будет указываться направление и расстояние по ' \
                   'прямой от ваших "домашних координат".'

    keyboard_settings = [[b_coords_check], [b_coords_del], [b_back_to_start]]
    reply_markup = ReplyKeyboardMarkup(keyboard_settings, resize_keyboard=True)

    data = {'text': bot_message, 'reply_markup': reply_markup,
            'parse_mode': 'HTML', 'disable_web_page_preview': True}
    process_sending_message_async(user_id=user_id, data=data)
    # msg_sent_by_specific_code = True

    # saving the last message from bot
    if not bot_request_aft_usr_msg:
        bot_request_aft_usr_msg = 'not_defined'

    try:
        cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))

        cur.execute("""INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);""",
                    (user_id, datetime.datetime.now(), bot_request_aft_usr_msg))

    except Exception as e:
        logging.info('failed to update the last saved message from bot')
        logging.exception(e)

    save_bot_reply_to_user(cur, user_id, bot_message)

    return None


def run_onboarding(user_id, username, onboarding_step_id, got_message):
    """part of the script responsible for orchestration of activities for non-finally-onboarded users"""

    if onboarding_step_id == 21:  # region_set
        # mark that onboarding is finished
        if got_message:
            save_onboarding_step(user_id, username, 'finished')
            onboarding_step_id = 80

    return onboarding_step_id


def compose_msg_on_user_setting_fullness(cur, user_id: int) -> Union[str, None]:
    """Create a text of message, which describes the degree on how complete user's profile is.
    More settings set – more complete profile it. It's done to motivate users to set the most tailored settings."""

    if not cur or not user_id:
        return None

    try:
        cur.execute("""SELECT
                            user_id 
                            , CASE WHEN role IS NOT NULL THEN TRUE ELSE FALSE END as role 
                            , CASE WHEN (SELECT TRUE FROM user_pref_age WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS age
                            , CASE WHEN (SELECT TRUE FROM user_coordinates WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS coords    
                            , CASE WHEN (SELECT TRUE FROM user_pref_radius WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS radius
                            , CASE WHEN (SELECT TRUE FROM user_pref_region WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS region
                            , CASE WHEN (SELECT TRUE FROM user_pref_topic_type WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS topic_type
                            , CASE WHEN (SELECT TRUE FROM user_pref_urgency WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS urgency
                            , CASE WHEN (SELECT TRUE FROM user_preferences WHERE user_id=%s 
                                AND preference!='bot_news' LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS notif_type
                            , CASE WHEN (SELECT TRUE FROM user_regional_preferences WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS region_old
                            , CASE WHEN (SELECT TRUE FROM user_forum_attributes WHERE user_id=%s
                                AND status = 'verified' LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS forum
                        FROM users WHERE user_id=%s;
                        """, (user_id, user_id, user_id, user_id, user_id,
                              user_id, user_id, user_id, user_id, user_id, ))

        raw_data = cur.fetchone()
        if not raw_data:
            return None

        _, pref_role, pref_age, pref_coords, pref_radius, pref_region, pref_topic_type, \
            pref_urgency, pref_notif_type, pref_region_old, pref_forum = raw_data

        list_of_settings = [pref_notif_type, pref_region_old, pref_coords, pref_radius, pref_age, pref_forum]
        user_score = int(round(sum(list_of_settings)/len(list_of_settings)*100, 0))

        logging.info(f'{list_of_settings}')
        logging.info(f'{user_score}')

        if user_score == 100:
            return None

        user_score_emoji = f'{user_score//10}\U0000FE0F\U000020E3{user_score-(user_score//10)*10}\U0000FE0F\U000020E3'
        message_text = f'Вы настроили бот на {user_score_emoji}%.\n\nЧтобы сделать бот максимально эффективным ' \
                       f'именно для вас, рекомендуем настроить следующие параметры:\n'
        if not pref_notif_type:
            message_text += ' - Тип уведомлений,\n'
        if not pref_region_old:
            message_text += ' - Регион,\n'
        if not pref_coords:
            message_text += ' - Домашние координаты,\n'
        if not pref_radius:
            message_text += ' - Максимальный радиус,\n'
        if not pref_age:
            message_text += ' - Возрастные группы БВП,\n'
        if not pref_forum:
            message_text += ' - Связать бот с форумом ЛА,\n'
        message_text = message_text[:-2]

        return message_text

    except Exception as e:
        logging.info(f'Exception in "compose_msg_on_user_setting_fullness" function')
        logging.exception(e)
        return None


def if_user_enables(text: str) -> Union[None, bool]:
    """check if user wants to enable or disable a feature"""
    user_wants_to_enable = None

    if text.find('☐') > -1:
        user_wants_to_enable = True
    elif text.find('☑') > -1:
        user_wants_to_enable = False

    return user_wants_to_enable


def save_last_user_inline_dialogue(cur, user_id: int, message_id: int) -> None:
    """Save to DB the user's last interaction via inline buttons"""

    cur.execute("""INSERT INTO communications_last_inline_msg 
                    (user_id, timestamp, message_id) values (%s, CURRENT_TIMESTAMP AT TIME ZONE 'UTC', %s)
                    ON CONFLICT (user_id) DO 
                    UPDATE SET timestamp=CURRENT_TIMESTAMP AT TIME ZONE 'UTC', message_id=%s;""",
                (user_id, message_id, message_id))
    return None


def get_last_user_inline_dialogue(cur, user_id: int) -> int:
    """Get from DB the user's last interaction via inline buttons"""

    cur.execute("""SELECT message_id FROM communications_last_inline_msg WHERE user_id=%s LIMIT 1;""",
                (user_id,))
    message_id = cur.fetchone()

    return message_id


def main(request):
    """Main function to orchestrate the whole script"""

    if request.method != "POST":
        logging.error(f'non-post request identified {request}')
        return 'it was not post request'

    bot_token = get_secrets("bot_api_token__prod")
    bot = Bot(token=bot_token)
    update = get_the_update(bot, request)

    user_new_status, timer_changed, photo, document, voice, contact, inline_query, sticker, user_latitude, \
        user_longitude, got_message, channel_type, username, user_id = get_basic_update_parameters(update)

    if timer_changed or photo or document or voice or sticker or (channel_type and user_id < 0) or \
            contact or inline_query:
        process_unneeded_messages(update, user_id, timer_changed, photo, document, voice, sticker, channel_type,
                                  contact, inline_query)
        return 'finished successfully. it was useless message for bot'

    if user_new_status in {'kicked', 'member'}:
        process_block_unblock_user(user_id, user_new_status)
        return 'finished successfully. it was a system message on bot block/unblock'

    b = AllButtons(full_buttons_dict)

    # Buttons & Keyboards
    # Start & Main menu
    b_start = '/start'

    b_role_iam_la = 'я состою в ЛизаАлерт'
    b_role_want_to_be_la = 'я хочу помогать ЛизаАлерт'
    b_role_looking_for_person = 'я ищу человека'
    b_role_other = 'у меня другая задача'
    b_role_secret = 'не хочу говорить'

    b_orders_done = 'да, заявки поданы'
    b_orders_tbd = 'нет, но я хочу продолжить'

    # TODO - WIP: FORUM
    b_forum_check_nickname = 'указать свой nickname с форума'
    b_forum_dont_have = 'у меня нет аккаунта на форуме ЛА'
    b_forum_dont_want = 'пропустить / не хочу говорить'
    # TODO ^^^

    # TODO – WIP: TOPIC TYPE
    b_topic_search_regular = 'стандартные активные поиски'
    b_topic_search_resonance = 'резонансные поиски в нескольких регионах'
    b_topic_search_info_support = 'информационная поддержка поисков'
    b_topic_search_patrol = 'патруль (только для некоторых регионов)'
    b_topic_search_reverse = 'обратные поиски (поиск родных)'
    b_topic_search_training = 'учебные поиски'
    b_topic_event = 'мероприятия'
    bd_topic_type = {'search_regular': b_topic_search_regular,
                     'search_resonance': b_topic_search_resonance,
                     'search_info_support': b_topic_search_info_support,
                     'search_patrol': b_topic_search_patrol,
                     'search_reverse': b_topic_search_reverse,
                     'search_training': b_topic_search_training,
                     'event': b_topic_event}

    modifiers = {'y': '☑', 'n': '☐'}

    # TODO ^^^

    b_pref_urgency_highest = 'самым первым (<2 минуты)'
    b_pref_urgency_high = 'пораньше (<5 минут)'
    b_pref_urgency_medium = 'могу ждать (<10 минут)'
    b_pref_urgency_low = 'не сильно важно (>10 минут)'

    b_yes_its_me = 'да, это я'
    b_no_its_not_me = 'нет, это не я'

    b_view_act_searches = 'посмотреть актуальные поиски'
    b_settings = 'настроить бот'
    b_other = 'другие возможности'
    keyboard_main = [[b_view_act_searches], [b_settings], [b_other]]
    reply_markup_main = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)

    # Settings menu
    b_set_pref_notif_type = 'настроить виды уведомлений'
    b_set_pref_coords = 'настроить "домашние координаты"'
    b_set_pref_radius = 'настроить максимальный радиус'
    b_set_pref_age = 'настроить возрастные группы БВП'
    b_set_pref_urgency = 'настроить скорость уведомлений'  # <-- TODO: likely to be removed as redundant
    b_set_pref_role = 'настроить вашу роль'  # <-- TODO
    b_set_forum_nick = 'связать аккаунты бота и форума'
    b_change_forum_nick = 'изменить аккаунт форума'
    b_set_topic_type = 'настроить вид интересующих поисков'  # <-- TODO

    b_back_to_start = 'в начало'

    # Settings - notifications
    b_act_all = 'включить: все уведомления'
    b_act_new_search = 'включить: о новых поисках'
    b_act_stat_change = 'включить: об изменениях статусов'
    b_act_all_comments = 'включить: о всех новых комментариях'
    b_act_inforg_com = 'включить: о комментариях Инфорга'
    b_act_field_trips_new = 'включить: о новых выездах'
    b_act_field_trips_change = 'включить: об изменениях в выездах'
    b_act_coords_change = 'включить: о смене места штаба'
    b_act_first_post_change = 'включить: об изменениях в первом посте'
    b_deact_all = 'настроить более гибко'
    b_deact_new_search = 'отключить: о новых поисках'
    b_deact_stat_change = 'отключить: об изменениях статусов'
    b_deact_all_comments = 'отключить: о всех новых комментариях'
    b_deact_inforg_com = 'отключить: о комментариях Инфорга'
    b_deact_field_trips_new = 'отключить: о новых выездах'
    b_deact_field_trips_change = 'отключить: об изменениях в выездах'
    b_deact_coords_change = 'отключить: о смене места штаба'
    b_deact_first_post_change = 'отключить: об изменениях в первом посте'

    # Settings - coordinates
    b_coords_auto_def = KeyboardButton(text='автоматически определить "домашние координаты"',
                                       request_location=True)
    b_coords_man_def = 'ввести "домашние координаты" вручную'
    b_coords_check = 'посмотреть сохраненные "домашние координаты"'
    b_coords_del = 'удалить "домашние координаты"'

    # Dialogue if Region – is Moscow
    b_reg_moscow = 'да, Москва – мой регион'
    b_reg_not_moscow = 'нет, я из другого региона'

    # Settings - Federal Districts
    b_fed_dist_dal_vos = 'Дальневосточный ФО'
    b_fed_dist_privolz = 'Приволжский ФО'
    b_fed_dist_sev_kaz = 'Северо-Кавказский ФО'
    b_fed_dist_sev_zap = 'Северо-Западный ФО'
    b_fed_dist_sibiria = 'Сибирский ФО'
    b_fed_dist_uralsky = 'Уральский ФО'
    b_fed_dist_central = 'Центральный ФО'
    b_fed_dist_yuzhniy = 'Южный ФО'
    b_fed_dist_other_r = 'Прочие поиски по РФ'
    b_fed_dist_pick_other = 'выбрать другой Федеральный Округ'
    keyboard_fed_dist_set = [[b_fed_dist_dal_vos],
                             [b_fed_dist_privolz],
                             [b_fed_dist_sev_kaz],
                             [b_fed_dist_sev_zap],
                             [b_fed_dist_sibiria],
                             [b_fed_dist_uralsky],
                             [b_fed_dist_central],
                             [b_fed_dist_yuzhniy],
                             [b_fed_dist_other_r],
                             [b_back_to_start]]

    # Settings - Dalnevostochniy Fed Dist - Regions
    b_reg_buryatiya = 'Бурятия'
    b_reg_prim_kray = 'Приморский край'
    b_reg_habarovsk = 'Хабаровский край'
    b_reg_amur = 'Амурская обл.'
    b_reg_dal_vost_other = 'Прочие поиски по ДФО'
    keyboard_dal_vost_reg_choice = [[b_reg_buryatiya],
                                    [b_reg_prim_kray],
                                    [b_reg_habarovsk],
                                    [b_reg_amur],
                                    [b_reg_dal_vost_other],
                                    [b_fed_dist_pick_other],
                                    [b_back_to_start]]

    # Settings - Privolzhskiy Fed Dist - Regions
    b_reg_bashkorkostan = 'Башкортостан'
    b_reg_kirov = 'Кировская обл.'
    b_reg_mariy_el = 'Марий Эл'
    b_reg_mordovia = 'Мордовия'
    b_reg_nizhniy = 'Нижегородская обл.'
    b_reg_orenburg = 'Оренбургская обл.'
    b_reg_penza = 'Пензенская обл.'
    b_reg_perm = 'Пермский край'
    b_reg_samara = 'Самарская обл.'
    b_reg_saratov = 'Саратовская обл.'
    b_reg_tatarstan = 'Татарстан'
    b_reg_udmurtiya = 'Удмуртия'
    b_reg_ulyanovsk = 'Ульяновская обл.'
    b_reg_chuvashiya = 'Чувашия'
    b_reg_privolz_other = 'Прочие поиски по ПФО'
    keyboard_privolz_reg_choice = [[b_reg_bashkorkostan],
                                   [b_reg_kirov],
                                   [b_reg_mariy_el],
                                   [b_reg_mordovia],
                                   [b_reg_nizhniy],
                                   [b_reg_orenburg],
                                   [b_reg_penza],
                                   [b_reg_perm],
                                   [b_reg_samara],
                                   [b_reg_saratov],
                                   [b_reg_tatarstan],
                                   [b_reg_udmurtiya],
                                   [b_reg_ulyanovsk],
                                   [b_reg_chuvashiya],
                                   [b_reg_privolz_other],
                                   [b_fed_dist_pick_other],
                                   [b_back_to_start]]

    # Settings - Severo-Kavkazskiy Fed Dist - Regions
    b_reg_dagestan = 'Дагестан'
    b_reg_stavropol = 'Ставропольский край'
    b_reg_chechnya = 'Чечня'
    b_reg_kabarda = 'Кабардино-Балкария'
    b_reg_ingushetia = 'Ингушетия'
    b_reg_sev_osetia = 'Северная Осетия'
    b_reg_sev_kav_other = 'Прочие поиски по СКФО'
    keyboard_sev_kav_reg_choice = [[b_reg_dagestan],
                                   [b_reg_stavropol],
                                   [b_reg_chechnya],
                                   [b_reg_kabarda],
                                   [b_reg_ingushetia],
                                   [b_reg_sev_osetia],
                                   [b_reg_sev_kav_other],
                                   [b_fed_dist_pick_other],
                                   [b_back_to_start]]

    # Settings - Severo-Zapadniy Fed Dist - Regions
    b_reg_vologda = 'Вологодская обл.'
    b_reg_karelia = 'Карелия'
    b_reg_komi = 'Коми'
    b_reg_piter = 'Ленинградская обл.'
    b_reg_murmansk = 'Мурманская обл.'
    b_reg_pskov = 'Псковская обл.'
    b_reg_archangelsk = 'Архангельская обл.'
    b_reg_sev_zap_other = 'Прочие поиски по СЗФО'
    keyboard_sev_zap_reg_choice = [[b_reg_vologda],
                                   [b_reg_komi],
                                   [b_reg_karelia],
                                   [b_reg_piter],
                                   [b_reg_murmansk],
                                   [b_reg_pskov],
                                   [b_reg_archangelsk],
                                   [b_reg_sev_zap_other],
                                   [b_fed_dist_pick_other],
                                   [b_back_to_start]]

    # Settings - Sibirskiy Fed Dist - Regions
    b_reg_altay = 'Алтайский край'
    b_reg_irkutsk = 'Иркутская обл.'
    b_reg_kemerovo = 'Кемеровская обл.'
    b_reg_krasnoyarsk = 'Красноярский край'
    b_reg_novosib = 'Новосибирская обл.'
    b_reg_omsk = 'Омская обл.'
    b_reg_tomsk = 'Томская обл.'
    b_reg_hakasiya = 'Хакасия'
    b_reg_sibiria_reg_other = 'Прочие поиски по СФО'
    keyboard_sibiria_reg_choice = [[b_reg_altay],
                                   [b_reg_irkutsk],
                                   [b_reg_kemerovo],
                                   [b_reg_krasnoyarsk],
                                   [b_reg_novosib],
                                   [b_reg_omsk],
                                   [b_reg_tomsk],
                                   [b_reg_hakasiya],
                                   [b_reg_sibiria_reg_other],
                                   [b_fed_dist_pick_other],
                                   [b_back_to_start]]

    # Settings - Uralskiy Fed Dist - Regions
    b_reg_ekat = 'Свердловская обл.'
    b_reg_kurgan = 'Курганская обл.'
    b_reg_tyumen = 'Тюменская обл.'
    b_reg_hanty_mansi = 'Ханты-Мансийский АО'
    b_reg_chelyabinks = 'Челябинская обл.'
    b_reg_yamal = 'Ямало-Ненецкий АО'
    b_reg_urals_reg_other = 'Прочие поиски по УФО'
    keyboard_urals_reg_choice = [[b_reg_ekat],
                                 [b_reg_kurgan],
                                 [b_reg_tyumen],
                                 [b_reg_hanty_mansi],
                                 [b_reg_chelyabinks],
                                 [b_reg_yamal],
                                 [b_reg_urals_reg_other],
                                 [b_fed_dist_pick_other],
                                 [b_back_to_start]]

    # Settings - Central Fed Dist - Regions
    b_reg_belogorod = 'Белгородская обл.'
    b_reg_bryansk = 'Брянская обл.'
    b_reg_vladimir = 'Владимирская обл.'
    b_reg_voronezh = 'Воронежская обл.'
    b_reg_ivanovo = 'Ивановская обл.'
    b_reg_kaluga = 'Калужская обл.'
    b_reg_kostroma = 'Костромская обл.'
    b_reg_kursk = 'Курская обл.'
    b_reg_lipetsk = 'Липецкая обл.'
    b_reg_msk_act = 'Москва и МО: Активные Поиски'
    b_reg_msk_inf = 'Москва и МО: Инфо Поддержка'
    b_reg_orel = 'Орловская обл.'
    b_reg_ryazan = 'Рязанская обл.'
    b_reg_smolensk = 'Смоленская обл.'
    b_reg_tambov = 'Тамбовская обл.'
    b_reg_tver = 'Тверская обл.'
    b_reg_tula = 'Тульская обл.'
    b_reg_yaroslavl = 'Ярославская обл.'
    b_reg_central_reg_other = 'Прочие поиски по ЦФО'
    keyboard_central_reg_choice = [[b_reg_belogorod],
                                   [b_reg_bryansk],
                                   [b_reg_vladimir],
                                   [b_reg_voronezh],
                                   [b_reg_ivanovo],
                                   [b_reg_kaluga],
                                   [b_reg_kostroma],
                                   [b_reg_kursk],
                                   [b_reg_lipetsk],
                                   [b_reg_msk_act],
                                   [b_reg_msk_inf],
                                   [b_reg_orel],
                                   [b_reg_ryazan],
                                   [b_reg_smolensk],
                                   [b_reg_tambov],
                                   [b_reg_tver],
                                   [b_reg_tula],
                                   [b_reg_yaroslavl],
                                   [b_reg_central_reg_other],
                                   [b_fed_dist_pick_other],
                                   [b_back_to_start]]

    # Settings - Yuzhniy Fed Dist - Regions
    b_reg_adygeya = 'Адыгея'
    b_reg_astrahan = 'Астраханская обл.'
    b_reg_volgograd = 'Волгоградская обл.'
    b_reg_krasnodar = 'Краснодарский край'
    b_reg_krym = 'Крым'
    b_reg_rostov = 'Ростовская обл.'
    b_reg_yuzhniy_reg_other = 'Прочие поиски по ЮФО'
    keyboard_yuzhniy_reg_choice = [[b_reg_adygeya],
                                   [b_reg_astrahan],
                                   [b_reg_volgograd],
                                   [b_reg_krasnodar],
                                   [b_reg_krym],
                                   [b_reg_rostov],
                                   [b_reg_yuzhniy_reg_other],
                                   [b_fed_dist_pick_other],
                                   [b_back_to_start]]

    # Settings - Fed Dist - Regions
    b_menu_set_region = 'настроить регион поисков'

    full_list_of_regions = keyboard_dal_vost_reg_choice[:-1] + keyboard_privolz_reg_choice[:-1] \
                           + keyboard_sev_kav_reg_choice[:-1] + keyboard_sev_zap_reg_choice[:-1] \
                           + keyboard_sibiria_reg_choice[:-1] + keyboard_urals_reg_choice[:-1] \
                           + keyboard_central_reg_choice[:-1] + keyboard_yuzhniy_reg_choice[:-1] \
                           + [[b_fed_dist_other_r]]  # noqa – for strange pycharm indent warning
    full_dict_of_regions = {word[0] for word in full_list_of_regions}

    dict_of_fed_dist = {b_fed_dist_dal_vos: keyboard_dal_vost_reg_choice,
                        b_fed_dist_privolz: keyboard_privolz_reg_choice,
                        b_fed_dist_sev_kaz: keyboard_sev_kav_reg_choice,
                        b_fed_dist_sev_zap: keyboard_sev_zap_reg_choice,
                        b_fed_dist_sibiria: keyboard_sibiria_reg_choice,
                        b_fed_dist_uralsky: keyboard_urals_reg_choice,
                        b_fed_dist_central: keyboard_central_reg_choice,
                        b_fed_dist_yuzhniy: keyboard_yuzhniy_reg_choice
                        }

    # Other menu
    b_view_latest_searches = 'посмотреть последние поиски'
    b_goto_community = 'написать разработчику бота'
    b_goto_first_search = 'ознакомиться с информацией для новичка'
    b_goto_photos = 'посмотреть красивые фото с поисков'
    keyboard_other = [[b_view_latest_searches], [b_goto_first_search],
                      [b_goto_community], [b_goto_photos], [b_back_to_start]]

    # Admin - specially keep it for Admin, regular users unlikely will be interested in it

    b_act_titles = 'названия'  # these are "Title update notification" button

    b_admin_menu = 'admin'
    b_test_menu = 'test'
    b_test_menu_2 = 'test2'

    b_pref_age_0_6_act = 'отключить: Маленькие Дети 0-6 лет'
    b_pref_age_0_6_deact = 'включить: Маленькие Дети 0-6 лет'
    b_pref_age_7_13_act = 'отключить: Подростки 7-13 лет'
    b_pref_age_7_13_deact = 'включить: Подростки 7-13 лет'
    b_pref_age_14_20_act = 'отключить: Молодежь 14-20 лет'
    b_pref_age_14_20_deact = 'включить: Молодежь 14-20 лет'
    b_pref_age_21_50_act = 'отключить: Взрослые 21-50 лет'
    b_pref_age_21_50_deact = 'включить: Взрослые 21-50 лет'
    b_pref_age_51_80_act = 'отключить: Старшее Поколение 51-80 лет'
    b_pref_age_51_80_deact = 'включить: Старшее Поколение 51-80 лет'
    b_pref_age_81_on_act = 'отключить: Старцы более 80 лет'
    b_pref_age_81_on_deact = 'включить: Старцы более 80 лет'

    b_pref_radius_act = 'включить ограничение по расстоянию'
    b_pref_radius_deact = 'отключить ограничение по расстоянию'
    b_pref_radius_change = 'изменить ограничение по расстоянию'

    b_help_yes = 'да, помогите мне настроить бот'
    b_help_no = 'нет, помощь не требуется'

    # basic markup which will be substituted for all specific cases
    reply_markup = reply_markup_main

    conn_psy = sql_connect_by_psycopg2()
    cur = conn_psy.cursor()

    if got_message:
        save_user_message_to_bot(cur, user_id, got_message)

    bot_request_aft_usr_msg = ''
    msg_sent_by_specific_code = False

    user_is_new = check_if_new_user(cur, user_id)
    if user_is_new:
        save_new_user(user_id, username)

    onboarding_step_id, onboarding_step_name = check_onboarding_step(cur, user_id, user_is_new)
    user_regions = get_user_reg_folders_preferences(cur, user_id)
    user_role = get_user_role(cur, user_id)

    # Check what was last request from bot and if bot is expecting user's input
    bot_request_bfr_usr_msg = get_last_bot_msg(cur, user_id)

    # placeholder for the New message from bot as reply to "update". Placed here – to avoid errors of GCF
    bot_message = ''

    # ONBOARDING PHASE
    if onboarding_step_id < 80:
        onboarding_step_id = run_onboarding(user_id, username, onboarding_step_id, got_message)

    # get coordinates from the text
    if bot_request_bfr_usr_msg == 'input_of_coords_man':
        user_latitude, user_longitude = get_coordinates_from_string(got_message, user_latitude, user_longitude)

    # if there is any coordinates from user
    if user_latitude and user_longitude:
        process_user_coordinates(cur, user_id, user_latitude, user_longitude, b_coords_check, b_coords_del,
                                 b_back_to_start, bot_request_aft_usr_msg)
        cur.close()
        conn_psy.close()

        return 'finished successfully. in was a message with user coordinates'

    try:

        # if there is a text message from user
        if got_message:

            # if pushed \start
            if got_message == b_start:

                if user_is_new:
                    bot_message = 'Привет! Это Бот Поисковика ЛизаАлерт. Он помогает Поисковикам ' \
                                  'оперативно получать информацию о новых поисках или об изменениях ' \
                                  'в текущих поисках.' \
                                  '\n\nБот управляется кнопками, которые заменяют обычную клавиатуру. ' \
                                  'Если кнопки не отображаются, справа от поля ввода сообщения ' \
                                  'есть специальный значок, чтобы отобразить кнопки управления ботом.' \
                                  '\n\nДавайте настроим бот индивидуально под вас. Пожалуйста, ' \
                                  'укажите вашу роль сейчас?'
                    keyboard_role = [[b_role_iam_la], [b_role_want_to_be_la],
                                     [b_role_looking_for_person], [b_role_other], [b_role_secret]]
                    reply_markup = ReplyKeyboardMarkup(keyboard_role, resize_keyboard=True)

                else:
                    bot_message = 'Привет! Бот управляется кнопками, которые заменяют обычную клавиатуру.'
                    reply_markup = reply_markup_main

            elif (onboarding_step_id == 20 and got_message in full_dict_of_regions) \
                    or got_message == b_reg_moscow:  # "moscow_replied"
                bot_message = '🎉 Отлично, вы завершили базовую настройку Бота.\n\n' \
                              'Список того, что сейчас умеет бот:\n' \
                              '- Высылает сводку по идущим поискам\n' \
                              '- Высылает сводку по последним поисками\n' \
                              '- Информирует о новых поисках с указанием расстояния до поиска\n' \
                              '- Информирует об изменении Статуса / Первого поста Инфорга\n' \
                              '- Информирует о новых комментариях Инфорга или пользователей\n' \
                              '- Позволяет гибко настроить информирование на основе удаленности от ' \
                              'вас, возраста пропавшего и т.п.\n\n' \
                              'С этого момента вы начнёте получать основные уведомления в ' \
                              'рамках выбранного региона, как только появятся новые изменения. ' \
                              'Или же вы сразу можете просмотреть списки Активных и Последних поисков.\n\n' \
                              'Бот приглашает вас настроить дополнительные параметры (можно пропустить):\n' \
                              '- Настроить виды уведомлений\n' \
                              '- Указать домашние координаты\n' \
                              '- Указать максимальный радиус до поиска\n' \
                              '- Указать возрастные группы пропавших\n' \
                              '- Связать бот с Форумом\n\n' \
                              'Создатели Бота надеются, что Бот сможет помочь вам в ваших задачах! Удачи!'

                keyboard_role = [[b_set_pref_notif_type], [b_set_pref_coords], [b_set_pref_radius],
                                 [b_set_pref_age], [b_set_forum_nick],
                                 [b_view_latest_searches], [b_view_act_searches], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_role, resize_keyboard=True)

                if got_message == b_reg_moscow:
                    bot_message, reply_markup = manage_if_moscow(cur, user_id, username, got_message,
                                                                 b_reg_moscow, b_reg_not_moscow,
                                                                 reply_markup, keyboard_fed_dist_set,
                                                                 bot_message, user_role)
                else:
                    save_onboarding_step(user_id, username, 'region_set')
                    save_user_pref_topic_type(cur, user_id, 'default', user_role)
                    updated_regions = update_and_download_list_of_regions(cur,
                                                                          user_id, got_message,
                                                                          b_menu_set_region,
                                                                          b_fed_dist_pick_other)

            elif got_message in {b_role_looking_for_person, b_role_want_to_be_la,
                                 b_role_iam_la, b_role_secret, b_role_other, b_orders_done, b_orders_tbd}:

                # save user role & onboarding stage
                if got_message in {b_role_want_to_be_la, b_role_iam_la, b_role_looking_for_person,
                                   b_role_other, b_role_secret}:
                    user_role = save_user_pref_role(cur, user_id, got_message)
                    save_onboarding_step(user_id, username, 'role_set')

                # get user role = relatives looking for a person
                if got_message == b_role_looking_for_person:

                    bot_message = 'Тогда вам следует:\n\n' \
                                  '1. Подайте заявку на поиск в ЛизаАлерт ОДНИМ ИЗ ДВУХ способов:\n' \
                                  '  1.1. САМОЕ БЫСТРОЕ – звоните на 88007005452 (бесплатная горячая ' \
                                  'линия ЛизаАлерт). Вам зададут ряд вопросов, который максимально ' \
                                  'ускорит поиск, и посоветуют дальнейшие действия. \n' \
                                  '  1.2. Заполните форму поиска https://lizaalert.org/zayavka-na-poisk/ \n' \
                                  'После заполнения формы на сайте нужно ожидать звонка от ЛизаАлерт. На ' \
                                  'обработку может потребоваться более часа. Если нет возможности ждать, ' \
                                  'после заполнения заявки следует позвонить на горячую линию отряда ' \
                                  '88007005452, сообщив, что вы уже оформили заявку на сайте.\n\n' \
                                  '2. Подать заявление в Полицию. Если иное не посоветовали на горячей линии,' \
                                  'заявка в Полицию – поможет ускорить и упростить поиск. Самый быстрый ' \
                                  'способ – позвонить на 102.\n\n' \
                                  '3. Отслеживайте ход поиска.\n' \
                                  'Когда заявки в ЛизаАлерт и Полицию сделаны, отряд начнет первые ' \
                                  'мероприятия для поиска человека: уточнение деталей, прозвоны ' \
                                  'в госучреждения, формирование плана и команды поиска и т.п. Весь этот' \
                                  'процесс вам не будет виден, но часто люди находятся именно на этой стадии' \
                                  'поиска. Если первые меры не помогут и отряд примет решение проводить' \
                                  'выезд "на место поиска" – тогда вы сможете отслеживать ход поиска ' \
                                  'через данный Бот, для этого продолжите настройку бота: вам нужно будет' \
                                  'указать ваш регион и выбрать, какие уведомления от бота вы будете ' \
                                  'получать. ' \
                                  'Как альтернатива, вы можете зайти на форум https://lizaalert.org/forum/, ' \
                                  'и отслеживать статус поиска там.\n' \
                                  'Отряд сделает всё возможное, чтобы найти вашего близкого как можно ' \
                                  'скорее.\n\n' \
                                  'Сообщите, подали ли вы заявки в ЛизаАлерт и Полицию?'

                    keyboard_orders = [[b_orders_done], [b_orders_tbd]]
                    reply_markup = ReplyKeyboardMarkup(keyboard_orders, resize_keyboard=True)

                # get user role = potential LA volunteer
                elif got_message == b_role_want_to_be_la:

                    bot_message = 'Супер! \n' \
                                  'Знаете ли вы, как можно помогать ЛизаАлерт? Определились ли вы, как ' \
                                  'вы готовы помочь? Если еще нет – не беда – рекомендуем ' \
                                  'ознакомиться со статьёй: ' \
                                  'https://takiedela.ru/news/2019/05/25/instrukciya-liza-alert/\n\n' \
                                  'Задачи, которые можно выполнять даже без специальной подготовки, ' \
                                  'выполняют Поисковики "на месте поиска". Этот Бот как раз старается ' \
                                  'помогать именно Поисковикам. ' \
                                  'Есть хороший сайт, рассказывающий, как начать участвовать в поиске: ' \
                                  'https://xn--b1afkdgwddgp9h.xn--p1ai/\n\n'\
                                  'В случае любых вопросов – не стесняйтесь, обращайтесь на общий телефон, ' \
                                  '8 800 700-54-52, где вам помогут с любыми вопросами при вступлении в отряд.\n\n' \
                                  'А если вы "из мира IT" и готовы помогать развитию этого Бота,' \
                                  'пишите нам в специальный чат https://t.me/+2J-kV0GaCgwxY2Ni\n\n' \
                                  'Надеемся, эта информацию оказалась полезной. ' \
                                  'Если вы готовы продолжить настройку Бота, уточните, пожалуйста: ' \
                                  'ваш основной регион – это Москва и Московская Область?'
                    keyboard_coordinates_admin = [[b_reg_moscow], [b_reg_not_moscow]]
                    reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

                # get user role = all others
                elif got_message in {b_role_iam_la, b_role_other, b_role_secret, b_orders_done, b_orders_tbd}:

                    bot_message = 'Спасибо. Теперь уточните, пожалуйста, ваш основной регион – это ' \
                                  'Москва и Московская Область?'
                    keyboard_coordinates_admin = [[b_reg_moscow], [b_reg_not_moscow]]
                    reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

            elif got_message in {b_reg_not_moscow}:
                bot_message, reply_markup = manage_if_moscow(cur, user_id, username, got_message,
                                                             b_reg_moscow, b_reg_not_moscow,
                                                             reply_markup_main, keyboard_fed_dist_set, None, user_role)

            elif got_message == b_help_no:

                bot_message = 'Спасибо, понятно. Мы записали. Тогда бот более не будет вас беспокоить, ' \
                              'пока вы сами не напишите в бот.\n\n' \
                              'На прощание, бот хотел бы посоветовать следующие вещи, делающие мир лучше:\n\n' \
                              '1. Посмотреть <a href="https://t.me/+6LYNNEy8BeI1NGUy">позитивные фото ' \
                              'с поисков ЛизаАлерт</a>.\n\n' \
                              '2. <a href="https://lizaalert.org/otryadnye-nuzhdy/">Помочь ' \
                              'отряду ЛизаАлерт, пожертвовав оборудование для поисков людей</a>.\n\n' \
                              '3. Помочь создателям данного бота, присоединившись к группе разработчиков' \
                              'или оплатив облачную инфраструктуру для бесперебойной работы бота. Для этого' \
                              '<a href="https://t.me/MikeMikeT">просто напишите разработчику бота</a>.\n\n' \
                              'Бот еще раз хотел подчеркнуть, что как только вы напишите что-то в бот – он' \
                              'сразу же "забудет", что вы ранее просили вас не беспокоить:)\n\n' \
                              'Обнимаем:)'
                keyboard = [[b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            elif got_message == b_help_yes:

                bot_message = 'Супер! Тогда давайте посмотрим, что у вас не настроено.\n\n' \
                              'У вас не настроен Регион поисков – без него Бот не может определить, ' \
                              'какие поиски вас интересуют. Вы можете настроить регион двумя способами:\n' \
                              '1. Либо автоматически на основании ваших координат – нужно будет отправить ' \
                              'вашу геолокацию (работает только с мобильных устройств),\n' \
                              '2. Либо выбрав регион вручную: для этого нужно сначала выбрать ФО = ' \
                              'Федеральный Округ, где находится ваш регион, а потом кликнуть на сам регион. ' \
                              '\n\n'

            # set user pref: urgency
            elif got_message in {b_pref_urgency_highest, b_pref_urgency_high,
                                 b_pref_urgency_medium, b_pref_urgency_low}:

                save_user_pref_urgency(cur, user_id, got_message, b_pref_urgency_highest,
                                       b_pref_urgency_high, b_pref_urgency_medium, b_pref_urgency_low)
                bot_message = 'Хорошо, спасибо. Бот запомнил ваш выбор.'

            # force user to input a region
            elif not user_regions \
                    and not (got_message in full_dict_of_regions or
                             got_message in dict_of_fed_dist or
                             got_message in {b_menu_set_region, b_start, b_settings}):

                bot_message = 'Для корректной работы бота, пожалуйста, задайте свой регион. Для этого ' \
                              'с помощью кнопок меню выберите сначала ФО (федеральный округ), а затем и ' \
                              'регион. Можно выбирать несколько регионов из разных ФО. Выбор региона ' \
                              'также можно отменить, повторно нажав на кнопку с названием региона. ' \
                              'Функционал бота не будет активирован, пока не выбран хотя бы один регион.'

                keyboard_coordinates_admin = [[b_menu_set_region]]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

                logging.info(f'user {user_id} is forced to fill in the region')

            # Send summaries
            elif got_message in {b_view_latest_searches, b_view_act_searches}:

                msg_sent_by_specific_code = True

                temp_dict = {b_view_latest_searches: 'all', b_view_act_searches: 'active'}

                cur.execute(
                    """
                    select forum_folder_id, folder_description from regions_to_folders;
                    """
                )

                folders_list = cur.fetchall()

                region_name = ''
                for region in user_regions:
                    for line in folders_list:

                        if line[0] == region:
                            region_name = line[1]
                            break

                    # check if region – is an archive folder: if so – it can be sent only to 'all'
                    if region_name.find('аверш') == -1 or temp_dict[got_message] == 'all':

                        bot_message = compose_full_message_on_list_of_searches(cur,
                                                                               temp_dict[got_message],
                                                                               user_id,
                                                                               region, region_name)
                        reply_markup = reply_markup_main

                        data = {'text': bot_message, 'reply_markup': reply_markup,
                                'parse_mode': 'HTML', 'disable_web_page_preview': True}
                        process_sending_message_async(user_id=user_id, data=data)

                        # saving the last message from bot
                        try:
                            cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))

                            cur.execute(
                                """
                                INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);
                                """,
                                (user_id, datetime.datetime.now(), 'report'))

                        except Exception as e:
                            logging.info('failed to save the last message from bot')
                            logging.exception(e)

            # Perform individual replies

            # Admin mode
            elif got_message.lower() == b_admin_menu:
                bot_message = "Вы вошли в специальный тестовый админ-раздел"

                # keyboard for Home Coordinates sharing
                keyboard_coordinates_admin = [[b_back_to_start], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

            # FIXME - WIP
            elif got_message.lower() == b_test_menu:
                bot_message = 'Вы в секретном тестовом разделе, где всё может работать не так :) ' \
                              'Если что – пишите, пожалуйста, в телеграм-чат ' \
                              'https://t.me/joinchat/2J-kV0GaCgwxY2Ni'
                keyboard_coordinates_admin = [[b_set_topic_type], [b_back_to_start]]
                # [b_set_pref_urgency], [b_set_forum_nick]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)
            # FIXME ^^^

            # FIXME – 17.11.2023 – playing with Inline buttons, trying to make them work in a nice way

            elif got_message.lower() == 'test3':
                bot_message = 'Вы в СУПЕР-секретном тестовом разделе 3'

                reply_markup = {"inline_keyboard": [
                    [{"text": "but_1", "callback_data": "but_1"}],
                    [{"text": "but_2", "callback_data": "but_2"}, {"text": "but_3", "callback_data": "but_3"}],
                    [{"text": "but_4", "callback_data": "but_4"}]
                    ]}

                # reply_markup = {"inline_keyboard": [[{"text": "but_1", "callback_data": "but_1"}]]}

            # FIXME ^^^

            elif got_message == b.set.topic_type.text or b.topic_types.contains(got_message):  # noqa
                bot_message, reply_markup = manage_topic_type_inline(cur, user_id, got_message, b)

            elif got_message in {b_set_pref_age, b_pref_age_0_6_act, b_pref_age_0_6_deact, b_pref_age_7_13_act,
                                 b_pref_age_7_13_deact, b_pref_age_14_20_act, b_pref_age_14_20_deact,
                                 b_pref_age_21_50_act, b_pref_age_21_50_deact, b_pref_age_51_80_act,
                                 b_pref_age_51_80_deact, b_pref_age_81_on_act, b_pref_age_81_on_deact}:

                input_data = None if got_message == b_set_pref_age else got_message
                keyboard, first_visit = manage_age(cur, user_id, input_data)
                keyboard.append([b_back_to_start])
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                if got_message.lower() == b_set_pref_age:
                    bot_message = 'Чтобы включить или отключить уведомления по определенной возрастной ' \
                                  'группе, нажмите на неё. Настройку можно изменить в любой момент.'
                    if first_visit:
                        bot_message = 'Данное меню позволяет выбрать возрастные категории БВП ' \
                                      '(без вести пропавших), по которым вы хотели бы получать уведомления. ' \
                                      'Важно, что если бот не сможет распознать возраст БВП, тогда вы ' \
                                      'всё равно получите уведомление.\nТакже данная настройка не влияет на ' \
                                      'разделы Актуальные Поиски и Последние Поиски – в них вы всё также ' \
                                      'сможете увидеть полный список поисков.\n\n' + bot_message
                else:
                    bot_message = 'Спасибо, записали.'

            elif got_message in {b_set_pref_radius, b_pref_radius_act, b_pref_radius_deact,
                                 b_pref_radius_change} or bot_request_bfr_usr_msg == 'radius_input':

                bot_message, reply_markup, bot_request_aft_usr_msg = \
                    manage_radius(cur, user_id, got_message, b_set_pref_radius, b_pref_radius_act,
                                  b_pref_radius_deact, b_pref_radius_change, b_back_to_start,
                                  b_set_pref_coords, bot_request_bfr_usr_msg)

            elif got_message in {b_set_forum_nick, b_yes_its_me, b_no_its_not_me} \
                    or bot_request_bfr_usr_msg == 'input_of_forum_username':

                bot_message, reply_markup, bot_request_aft_usr_msg = \
                    manage_linking_to_forum(cur, got_message, user_id, b_set_forum_nick, b_back_to_start,
                                            bot_request_bfr_usr_msg, b_admin_menu, b_test_menu, b_yes_its_me,
                                            b_no_its_not_me, b_settings, reply_markup_main)

            elif got_message == b_set_pref_urgency:

                bot_message = 'Очень многие поисковики пользуются этим Ботом. При любой рассылке нотификаций' \
                              ' Бот ставит все сообщения в очередь, и они обрабатываются ' \
                              'со скоростью, ограниченной технологиями Телеграма. Иногда, в случае нескольких' \
                              ' больших поисков, очередь вырастает и кто-то получает сообщения практически ' \
                              'сразу, а кому-то они приходят с задержкой.\n' \
                              'Вы можете помочь сделать рассылки уведомлений более "нацеленными", обозначив ' \
                              'с какой срочностью вы бы хотели получать уведомления от Бота. В скобках ' \
                              'указаны примерные сроки задержки относительно появления информации на форуме. ' \
                              'Выберите наиболее подходящий Вам вариант'
                keyboard = [[b_pref_urgency_highest], [b_pref_urgency_high], [b_pref_urgency_medium],
                            [b_pref_urgency_low], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            # DEBUG: for debugging purposes only
            elif got_message.lower() == 'go':
                publish_to_pubsub('topic_notify_admin', 'test_admin_check')

            elif got_message == b_other:
                bot_message = 'Здесь можно посмотреть статистику по 20 последним поискам, перейти в ' \
                              'канал Коммъюнити или Прочитать важную информацию для Новичка и посмотреть ' \
                              'душевные фото с поисков'
                reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

            elif got_message in {b_menu_set_region, b_fed_dist_pick_other}:
                bot_message = update_and_download_list_of_regions(cur,
                                                                  user_id, got_message,
                                                                  b_menu_set_region,
                                                                  b_fed_dist_pick_other)
                reply_markup = ReplyKeyboardMarkup(keyboard_fed_dist_set, resize_keyboard=True)

            elif got_message in dict_of_fed_dist:
                updated_regions = update_and_download_list_of_regions(cur,
                                                                      user_id, got_message,
                                                                      b_menu_set_region,
                                                                      b_fed_dist_pick_other)
                bot_message = updated_regions
                reply_markup = ReplyKeyboardMarkup(dict_of_fed_dist[got_message], resize_keyboard=True)

            elif got_message in full_dict_of_regions:
                updated_regions = update_and_download_list_of_regions(cur,
                                                                      user_id, got_message,
                                                                      b_menu_set_region,
                                                                      b_fed_dist_pick_other)
                bot_message = updated_regions
                keyboard = keyboard_fed_dist_set
                for fed_dist in dict_of_fed_dist:
                    for region in dict_of_fed_dist[fed_dist]:
                        if region[0] == got_message:
                            keyboard = dict_of_fed_dist[fed_dist]
                            break
                    else:
                        continue
                    break
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                if onboarding_step_id == 20:  # "moscow_replied"
                    save_onboarding_step(user_id, username, 'region_set')
                    save_user_pref_topic_type(cur, user_id, 'default', user_role)

            elif got_message == b_settings:
                bot_message = 'Это раздел с настройками. Здесь вы можете выбрать удобные для вас ' \
                              'уведомления, а также ввести свои "домашние координаты", на основе которых ' \
                              'будет рассчитываться расстояние и направление до места поиска. Вы в любой ' \
                              'момент сможете изменить эти настройки.'

                message_prefix = compose_msg_on_user_setting_fullness(cur, user_id)
                if message_prefix:
                    bot_message = f'{bot_message}\n\n{message_prefix}'

                keyboard_settings = [[b_set_pref_notif_type], [b_menu_set_region], [b_set_pref_coords],
                                     [b_set_pref_radius], [b_set_pref_age], [b_set_forum_nick],
                                     [b_back_to_start]]  # #AK added b_set_forum_nick for issue #6
                reply_markup = ReplyKeyboardMarkup(keyboard_settings, resize_keyboard=True)

            elif got_message == b_set_pref_coords:
                bot_message = 'АВТОМАТИЧЕСКОЕ ОПРЕДЕЛЕНИЕ координат работает только для носимых устройств' \
                              ' (для настольных компьютеров – НЕ работает: используйте, пожалуйста, ' \
                              'кнопку ручного ввода координат). ' \
                              'При автоматическом определении координат – нажмите на кнопку и ' \
                              'разрешите определить вашу текущую геопозицию. ' \
                              'Координаты, загруженные вручную или автоматически, будут считаться ' \
                              'вашим "домом", откуда будут рассчитаны расстояние и ' \
                              'направление до поисков.'
                keyboard_coordinates_1 = [[b_coords_auto_def], [b_coords_man_def], [b_coords_check],
                                          [b_coords_del], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

            elif got_message == b_coords_del:
                delete_user_coordinates(cur, user_id)
                bot_message = 'Ваши "домашние координаты" удалены. Теперь расстояние и направление ' \
                              'до поисков не будет отображаться.\n' \
                              'Вы в любой момент можете заново ввести новые "домашние координаты". ' \
                              'Функция Автоматического определения координат работает только для ' \
                              'носимых устройств, для настольного компьютера – воспользуйтесь ' \
                              'ручным вводом.'
                keyboard_coordinates_1 = [[b_coords_auto_def], [b_coords_man_def], [b_coords_check],
                                          [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

            elif got_message == b_coords_man_def:
                bot_message = 'Введите координаты вашего дома вручную в теле сообщения и просто ' \
                              'отправьте. Формат: XX.XXXХХ, XX.XXXХХ, где количество цифр после точки ' \
                              'может быть различным. Широта (первое число) должна быть между 30 ' \
                              'и 80, Долгота (второе число) – между 10 и 190.'
                bot_request_aft_usr_msg = 'input_of_coords_man'
                reply_markup = ReplyKeyboardRemove()

            elif got_message == b_coords_check:

                lat, lon = show_user_coordinates(cur, user_id)
                if lat and lon:
                    bot_message = 'Ваши "домашние координаты" '
                    bot_message += generate_yandex_maps_place_link(lat, lon, 'coords')

                else:
                    bot_message = 'Ваши координаты пока не сохранены. Введите их автоматически или вручную.'

                keyboard_coordinates_1 = [[b_coords_auto_def], [b_coords_man_def],
                                          [b_coords_check], [b_coords_del], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

            elif got_message == b_back_to_start:
                bot_message = 'возвращаемся в главное меню'
                reply_markup = reply_markup_main

            elif got_message == b_goto_community:
                bot_message = 'Бот можно обсудить с соотрядниками в ' \
                              '<a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальном Чате ' \
                              'в телеграм</a>. Там можно предложить свои идеи, указать на проблемы ' \
                              'и получить быструю обратную связь от разработчика.'
                keyboard_other = [[b_view_latest_searches], [b_goto_first_search],
                                  [b_goto_photos], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

            elif got_message == b_goto_first_search:
                bot_message = 'Если вы хотите стать добровольцем ДПСО «ЛизаАлерт», пожалуйста, ' \
                              '<a href="https://lizaalert.org/forum/viewtopic.php?t=56934">' \
                              'посетите страницу форума</a>, там можно ознакомиться с базовой информацией ' \
                              'для новичков и задать свои вопросы.' \
                              'Если вы готовитесь к своему первому поиску – приглашаем ' \
                              '<a href="https://xn--b1afkdgwddgp9h.xn--p1ai/">ознакомиться с основами ' \
                              'работы ЛА</a>. Всю теорию работы ЛА необходимо получать от специально ' \
                              'обученных волонтеров ЛА. Но если у вас еще не было возможности пройти ' \
                              'официальное обучение, а вы уже готовы выехать на поиск – этот ресурс ' \
                              'для вас.'
                keyboard_other = [[b_view_latest_searches], [b_goto_community],
                                  [b_goto_photos], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

            elif got_message == b_goto_photos:
                bot_message = 'Если вам хочется окунуться в атмосферу ПСР, приглашаем в замечательный ' \
                              '<a href="https://t.me/+6LYNNEy8BeI1NGUy">телеграм-канал с красивыми фото с ' \
                              'поисков</a>. Все фото – сделаны поисковиками во время настоящих ПСР.'
                keyboard_other = [[b_view_latest_searches], [b_goto_community], [b_goto_first_search],
                                  [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

            # special block for flexible menu on notification preferences
            elif got_message in {b_act_all, b_deact_all,
                                 b_act_new_search, b_act_stat_change, b_act_titles, b_act_all_comments,
                                 b_set_pref_notif_type, b_deact_stat_change, b_deact_all_comments,
                                 b_deact_new_search,
                                 b_act_inforg_com, b_deact_inforg_com,
                                 b_act_field_trips_new, b_deact_field_trips_new,
                                 b_act_field_trips_change, b_deact_field_trips_change,
                                 b_act_coords_change, b_deact_coords_change,
                                 b_act_first_post_change, b_deact_first_post_change}:

                # save preference for +ALL
                if got_message == b_act_all:
                    bot_message = 'Супер! теперь вы будете получать уведомления в телеграм в случаях: ' \
                                  'появление нового поиска, изменение статуса поиска (стоп, НЖ, НП), ' \
                                  'появление новых комментариев по всем поискам. Вы в любой момент ' \
                                  'можете изменить список уведомлений'
                    save_preference(cur, user_id, 'all')

                # save preference for -ALL
                elif got_message == b_deact_all:
                    bot_message = 'Вы можете настроить типы получаемых уведомлений более гибко'
                    save_preference(cur, user_id, '-all')

                # save preference for +NEW SEARCHES
                elif got_message == b_act_new_search:
                    bot_message = 'Отлично! Теперь вы будете получать уведомления в телеграм при ' \
                                  'появлении нового поиска. Вы в любой момент можете изменить ' \
                                  'список уведомлений'
                    save_preference(cur, user_id, 'new_searches')

                # save preference for -NEW SEARCHES
                elif got_message == b_deact_new_search:
                    bot_message = 'Записали'
                    save_preference(cur, user_id, '-new_searches')

                # save preference for +STATUS UPDATES
                elif got_message == b_act_stat_change:
                    bot_message = 'Отлично! теперь вы будете получать уведомления в телеграм при ' \
                                  'изменении статуса поисков (НЖ, НП, СТОП и т.п.). Вы в любой момент ' \
                                  'можете изменить список уведомлений'
                    save_preference(cur, user_id, 'status_changes')

                # save preference for -STATUS UPDATES
                elif got_message == b_deact_stat_change:
                    bot_message = 'Записали'
                    save_preference(cur, user_id, '-status_changes')

                # save preference for TITLE UPDATES
                elif got_message == b_act_titles:
                    bot_message = 'Отлично!'
                    save_preference(cur, user_id, 'title_changes')

                # save preference for +COMMENTS
                elif got_message == b_act_all_comments:
                    bot_message = 'Отлично! Теперь все новые комментарии будут у вас! Вы в любой момент ' \
                                  'можете изменить список уведомлений'
                    save_preference(cur, user_id, 'comments_changes')

                # save preference for -COMMENTS
                elif got_message == b_deact_all_comments:
                    bot_message = 'Записали. Мы только оставили вам включенными уведомления о ' \
                                  'комментариях Инфорга. Их тоже можно отключить'
                    save_preference(cur, user_id, '-comments_changes')

                # save preference for +InforgComments
                elif got_message == b_act_inforg_com:
                    bot_message = 'Если вы не подписаны на уведомления по всем комментариям, то теперь ' \
                                  'вы будете получать уведомления о комментариях от Инфорга. Если же вы ' \
                                  'уже подписаны на все комментарии – то всё остаётся без изменений: бот ' \
                                  'уведомит вас по всем комментариям, включая от Инфорга'
                    save_preference(cur, user_id, 'inforg_comments')

                # save preference for -InforgComments
                elif got_message == b_deact_inforg_com:
                    bot_message = 'Вы отписались от уведомлений по новым комментариям от Инфорга'
                    save_preference(cur, user_id, '-inforg_comments')

                # save preference for +FieldTripsNew
                elif got_message == b_act_field_trips_new:
                    bot_message = 'Теперь вы будете получать уведомления о новых выездах по уже идущим ' \
                                  'поискам. Обратите внимание, что это не рассылка по новым темам на ' \
                                  'форуме, а именно о том, что в существующей теме в ПЕРВОМ посте ' \
                                  'появилась информация о новом выезде'
                    save_preference(cur, user_id, 'field_trips_new')

                # save preference for -FieldTripsNew
                elif got_message == b_deact_field_trips_new:
                    bot_message = 'Вы отписались от уведомлений по новым выездам'
                    save_preference(cur, user_id, '-field_trips_new')

                # save preference for +FieldTripsChange
                elif got_message == b_act_field_trips_change:
                    bot_message = 'Теперь вы будете получать уведомления о ключевых изменениях при ' \
                                  'выездах, в т.ч. изменение или завершение выезда. Обратите внимание, ' \
                                  'что эта рассылка отражает изменения только в ПЕРВОМ посте поиска.'
                    save_preference(cur, user_id, 'field_trips_change')

                # save preference for -FieldTripsChange
                elif got_message == b_deact_field_trips_change:
                    bot_message = 'Вы отписались от уведомлений по изменениям выездов'
                    save_preference(cur, user_id, '-field_trips_change')

                # save preference for +CoordsChange
                elif got_message == b_act_coords_change:
                    bot_message = 'Если у штаба поменяются координаты (и об этом будет написано в первом ' \
                                  'посте на форуме) – бот уведомит вас об этом'
                    save_preference(cur, user_id, 'coords_change')

                # save preference for -CoordsChange
                elif got_message == b_deact_coords_change:
                    bot_message = 'Вы отписались от уведомлений о смене места (координат) штаба'
                    save_preference(cur, user_id, '-coords_change')

                # save preference for -FirstPostChanges
                elif got_message == b_act_first_post_change:
                    bot_message = 'Теперь вы будете получать уведомления о важных изменениях в Первом Посте' \
                                  ' Инфорга, где обозначено описание каждого поиска'
                    save_preference(cur, user_id, 'first_post_changes')

                # save preference for -FirstPostChanges
                elif got_message == b_deact_first_post_change:
                    bot_message = 'Вы отписались от уведомлений о важных изменениях в Первом Посте' \
                                  ' Инфорга c описанием каждого поиска'
                    save_preference(cur, user_id, '-first_post_changes')

                # GET what are preferences
                elif got_message == b_set_pref_notif_type:
                    prefs = compose_user_preferences_message(cur, user_id)
                    if prefs[0] == 'пока нет включенных уведомлений' or prefs[0] == 'неизвестная настройка':
                        bot_message = 'Выберите, какие уведомления вы бы хотели получать'
                    else:
                        bot_message = 'Сейчас у вас включены следующие виды уведомлений:\n'
                        bot_message += prefs[0]

                else:
                    bot_message = 'empty message'

                if got_message == b_act_all:
                    keyboard_notifications_flexible = [[b_deact_all], [b_back_to_start]]
                elif got_message == b_deact_all:
                    keyboard_notifications_flexible = [[b_act_all], [b_deact_new_search],
                                                       [b_deact_stat_change], [b_act_all_comments],
                                                       [b_deact_inforg_com], [b_deact_first_post_change],
                                                       [b_back_to_start]]
                else:

                    # getting the list of user notification preferences
                    prefs = compose_user_preferences_message(cur, user_id)
                    keyboard_notifications_flexible = [[b_act_all], [b_act_new_search], [b_act_stat_change],
                                                       [b_act_all_comments], [b_act_inforg_com],
                                                       [b_act_first_post_change],
                                                       [b_back_to_start]]

                    for line in prefs[1]:
                        if line == 'all':
                            keyboard_notifications_flexible = [[b_deact_all], [b_back_to_start]]
                        elif line == 'new_searches':
                            keyboard_notifications_flexible[1] = [b_deact_new_search]
                        elif line == 'status_changes':
                            keyboard_notifications_flexible[2] = [b_deact_stat_change]
                        elif line == 'comments_changes':
                            keyboard_notifications_flexible[3] = [b_deact_all_comments]
                        elif line == 'inforg_comments':
                            keyboard_notifications_flexible[4] = [b_deact_inforg_com]
                        elif line == 'first_post_changes':
                            keyboard_notifications_flexible[5] = [b_deact_first_post_change]

                reply_markup = ReplyKeyboardMarkup(keyboard_notifications_flexible, resize_keyboard=True)

            # in case of other user messages:
            else:
                # If command in unknown
                bot_message = 'не понимаю такой команды, пожалуйста, используйте кнопки со стандартными ' \
                              'командами ниже'
                reply_markup = reply_markup_main

            if not msg_sent_by_specific_code:

                # FIXME – 17.11.2023 – migrating from async to pure api call
                admin_id = int(get_secrets('my_telegram_id'))
                if user_id != admin_id:
                    data = {'text': bot_message, 'reply_markup': reply_markup,
                            'parse_mode': 'HTML', 'disable_web_page_preview': True}
                    process_sending_message_async(user_id=user_id, data=data)
                else:
                    if not isinstance(reply_markup, dict):
                        reply_markup = reply_markup.to_dict()
                    params = {'parse_mode': 'HTML', 'disable_web_page_preview': True, 'reply_markup': reply_markup}
                    result = send_message_to_api(bot_token, user_id, bot_message, params)
                    notify_admin(f'RESULT {result}')
                # FIXME ^^^

            # saving the last message from bot
            if not bot_request_aft_usr_msg:
                bot_request_aft_usr_msg = 'not_defined'

            try:
                cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))

                cur.execute(
                    """
                    INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);
                    """,
                    (user_id, datetime.datetime.now(), bot_request_aft_usr_msg))

            except Exception as e:
                logging.info(f'failed updates of table msg_from_bot for user={user_id}')
                logging.exception(e)

        # all other cases when bot was not able to understand the message from user
        else:
            logging.info('DBG.C.6. THERE IS a COMM SCRIPT INVOCATION w/O MESSAGE:')
            logging.info(str(update))
            text_for_admin = f'[comm]: Empty message in Comm, user={user_id}, username={username}, ' \
                             f'got_message={got_message}, update={update}, ' \
                             f'bot_request_bfr_usr_msg={bot_request_bfr_usr_msg}'
            logging.info(text_for_admin)
            notify_admin(text_for_admin)

    except Exception as e:
        logging.info('GENERAL COMM CRASH:')
        logging.exception(e)
        notify_admin('[comm] general script fail')

    if bot_message:
        save_bot_reply_to_user(cur, user_id, bot_message)

    cur.close()
    conn_psy.close()

    return 'finished successfully. in was a regular conversational message'
