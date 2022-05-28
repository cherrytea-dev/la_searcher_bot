import os
import datetime
import re
import json
import logging
import qrcode
from io import BytesIO

import psycopg2
from psycopg2 import sql

from telegram import ReplyKeyboardMarkup, ForceReply, KeyboardButton, Bot, Update

from google.cloud import secretmanager, pubsub_v1, storage


# done to exclude warnings in PyCharm
class MockClass1:

    @staticmethod
    def execute(a, b=None):
        pass

    @staticmethod
    def fetchone():
        return []


# done to exclude warnings in PyCharm
class MockClass2:

    @staticmethod
    def commit():
        pass


db = None
cur = MockClass1()
conn_psy = MockClass2()
local_development = False
# bot = None
# bot_debug = None
admin_user_id = None
coordinates_format = "{0:.5f}"

publisher = pubsub_v1.PublisherClient()
project_id = os.environ["GCP_PROJECT"]
client = secretmanager.SecretManagerServiceClient()


def get_secrets(secret_request):
    name = f"projects/{project_id}/secrets/{secret_request}/versions/latest"
    # noinspection PyUnresolvedReferences
    response = client.access_secret_version(name=name)

    return response.payload.data.decode("UTF-8")


def sql_connect_by_psycopg2():
    global cur
    global conn_psy

    db_user = get_secrets("cloud-postgres-username")
    db_pass = get_secrets("cloud-postgres-password")
    db_name = get_secrets("cloud-postgres-db-name")
    db_conn = get_secrets("cloud-postgres-connection-name")
    db_host = '/cloudsql/' + db_conn

    conn_psy = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_pass)
    cur = conn_psy.cursor()

    return None


def publish_to_pubsub(topic_name, message):
    global project_id
    global publisher

    # Preparing to turn to the existing pub/sub topic
    topic_path = publisher.topic_path(project_id, topic_name)

    # Prepare the message
    message_json = json.dumps({'data': {'message': message}, })
    message_bytes = message_json.encode('utf-8')

    # Publish the message
    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify that publishing succeeded
        logging.info('Pub/sub message was published')

    except Exception as e:
        logging.info('Pub/sub message was NOT published')
        logging.exception(e)

    return None


def time_counter_since_search_start(start_time):
    start_diff = datetime.timedelta(hours=0)

    now = datetime.datetime.now()
    diff = now - start_time - start_diff

    # first_word_parameter = 'Ищем '
    first_word_parameter = ''

    # меньше 20 минут - начинаем искать
    if (diff.total_seconds() / 60) < 20:
        phrase = 'Начинаем искать'

    # 20 минут-1 час - Ищем ХХ минут
    elif (diff.total_seconds() / 3600) < 1:
        phrase = first_word_parameter + str(round(int(diff.total_seconds() / 60), -1)) + ' минут'

    # 1-24 часа - Ищем ХХ часов
    elif diff.days < 1:
        phrase = first_word_parameter + str(int(diff.total_seconds() / 3600))
        if int(diff.total_seconds() / 3600) in {1, 21}:
            phrase += ' час'
        elif int(diff.total_seconds() / 3600) in {2, 3, 4, 22, 23}:
            phrase += ' часа'
        else:
            phrase += ' часов'

    # больше 24 часов - Ищем Х дней
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


def send_user_preferences(input_user_id):
    global cur
    global conn_psy

    # noinspection PyUnresolvedReferences
    cur.execute("""SELECT preference FROM user_preferences WHERE user_id=%s ORDER BY preference;""", (input_user_id,))
    # noinspection PyUnresolvedReferences
    conn_psy.commit()
    user_prefs = cur.fetchall()

    prefs_wording = ''
    prefs_list = []
    if user_prefs and len(user_prefs) > 0:
        for i in range(len(user_prefs)):
            user_pref_line = user_prefs[i]
            prefs_list.append(user_pref_line[0])
            if user_pref_line[0] == 'all':
                prefs_wording += 'все сообщения'
            elif user_pref_line[0] == 'start':
                prefs_wording += 'пока нет включенных уведомлений'
            elif user_pref_line[0] == 'finish':
                prefs_wording += 'пока нет включенных уведомлений'
            elif user_pref_line[0] == 'new_searches':
                prefs_wording += ' &#8226; о новых поисках\n'
            elif user_pref_line[0] == 'status_changes':
                prefs_wording += ' &#8226; об изменении статуса\n'
            elif user_pref_line[0] == 'title_changes':
                prefs_wording += ' &#8226; об изменении названия\n'
            elif user_pref_line[0] == 'comments_changes':
                prefs_wording += ' &#8226; о всех комментариях\n'
            elif user_pref_line[0] == 'inforg_comments':
                prefs_wording += ' &#8226; о комментариях Инфорга\n'
            elif user_pref_line[0] == 'bot_news':
                prefs_wording += ' &#8226; о новых функциях бота\n'
            else:
                prefs_wording += 'неизвестная настройка'
    else:
        prefs_wording += 'пока нет включенных уведомлений'

    prefs_wording_and_list = [prefs_wording, prefs_list]

    return prefs_wording_and_list


def define_family_name(title_string):
    """TO BE DELETED and FAM NAME to be TAKEN from SEARCHES Table and field NAME"""
    # TODO: add family_name from Searches table directly

    string_by_word = title_string.split()

    # exception case: when Family Name is third word
    # it happens when first two either Найден Жив or Найден Погиб with different word forms
    if string_by_word[0][0:4].lower() == "найд":
        fam_name = string_by_word[2]

    # case when "Поиск приостановлен"
    elif string_by_word[1][0:8].lower() == 'приостан':
        fam_name = string_by_word[2]

    # case when "Поиск завершен"
    elif string_by_word[1][0:6].lower() == 'заверш':
        fam_name = string_by_word[2]

    # all the other cases
    else:
        fam_name = string_by_word[1]

    return fam_name


def compose_msg_on_all_last_searches(region):
    global cur
    global conn_psy

    msg = ''

    # download the list from SEARCHES sql table
    cur.execute(
        """select s2.* from (SELECT search_forum_num, parsed_time, status_short, forum_search_title, cut_link, 
        search_start_time, num_of_replies, family_name, age, id, forum_folder_id FROM searches WHERE 
        forum_folder_id=%s ORDER BY search_start_time DESC LIMIT 20) s2 LEFT JOIN 
        search_health_check shc ON s2.search_forum_num=shc.search_forum_num 
        WHERE (shc.status is NULL or shc.status='ok') 
        ORDER BY s2.search_start_time DESC;""", (region,)
    )
    conn_psy.commit()
    database = cur.fetchall()

    for db_line in database:

        if str(db_line[2])[0:4] == 'Ищем':
            msg += 'Ищем ' + time_counter_since_search_start(db_line[5])[0]
        else:
            msg += db_line[2]

        msg += ' <a href="https://lizaalert.org/forum/viewtopic.php?t=' + str(db_line[0]) + '">'

        if db_line[7]:
            family_name = db_line[7]
        else:
            family_name = define_family_name(db_line[3])

        msg += family_name

        first_letter = str(family_name)[0]
        if first_letter.isupper() and db_line[8] and db_line[8] != 0:
            msg += ' '
            msg += age_writer(db_line[8])
        msg += '</a>\n'

    return msg


def compose_msg_on_active_searches_in_one_reg(region, user_data):
    global cur
    global conn_psy

    msg = ''

    # download the list from SEARCHES sql table
    cur.execute(
        """select s2.* from (SELECT s.search_forum_num, s.parsed_time, s.status_short, s.forum_search_title, s.cut_link, 
        s.search_start_time, s.num_of_replies, s.family_name, s.age, s.id, sa.id, sa.search_id, 
        sa.activity_type, sa.latitude, sa.longitude, sa.upd_time, sa.coord_type, s.forum_folder_id FROM 
        searches s LEFT JOIN search_coordinates sa ON s.search_forum_num = sa.search_id WHERE 
        s.status_short='Ищем' AND s.forum_folder_id=%s ORDER BY s.search_start_time DESC) s2 LEFT JOIN 
        search_health_check shc ON s2.search_forum_num=shc.search_forum_num 
        WHERE (shc.status is NULL or shc.status='ok') ORDER BY s2.search_start_time DESC;""", (region,)
    )
    conn_psy.commit()
    database = cur.fetchall()

    user_lat = None
    user_lon = None

    if user_data:
        user_lat = user_data[0]
        user_lon = user_data[1]

    for db_line in database:

        if time_counter_since_search_start(db_line[5])[1] < 60:

            # time since search start
            msg += time_counter_since_search_start(db_line[5])[0]

            # distance & direction
            if user_lat is not None:
                if db_line[13] is not None:
                    dist = distance_to_search(db_line[13], db_line[14], user_lat, user_lon)
                    msg += ' ' + dist[1] + ' ' + str(dist[0]) + ' км'
            msg += ' <a href="https://lizaalert.org/forum/viewtopic.php?t=' + str(db_line[0]) + '">'

            if db_line[7]:
                family_name = db_line[7]
            else:
                family_name = define_family_name(db_line[3])
            msg += family_name
            first_letter = str(family_name)[0]
            if first_letter.isupper() and db_line[8] and db_line[8] != 0:
                msg += ' '
                msg += age_writer(db_line[8])
            msg += '</a>\n'

    return msg


def send_a_list_of_searches(list_type, curr_user_id, region, region_name):
    global cur
    global conn_psy
    msg = ''

    cur.execute(
        "SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;", (curr_user_id,)
    )
    conn_psy.commit()
    user_data = cur.fetchone()

    # combine the list of last 20 searches
    if list_type == 'all':

        msg += compose_msg_on_all_last_searches(region)

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

        msg += compose_msg_on_active_searches_in_one_reg(region, user_data)

        if msg:
            msg = 'Актуальные поиски за 60 дней в разделе <a href="https://lizaalert.org/forum/viewforum.php?f=' \
                  + str(region) + '">' + region_name + '</a>:\n' + msg

        else:
            msg = 'В разделе <a href="https://lizaalert.org/forum/viewforum.php?f=' \
                  + str(region) + '">' + region_name + '</a> все поиски за последние 60 дней завершены.'

    return msg


def save_new_user(input_user_id, input_username):
    """save the new user in all the user-related tables"""

    global cur
    global conn_psy

    # add the New User into table users
    cur.execute("""INSERT INTO users (user_id, username_telegram, reg_date) values (%s, %s, %s);""",
                (input_user_id, input_username, datetime.datetime.now()))
    conn_psy.commit()

    # add the New User into table user_preferences
    # default setting is set as notifications on new searches & status changes
    cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                (input_user_id, 'new_searches', 0))
    conn_psy.commit()
    cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                (input_user_id, 'status_changes', 1))
    conn_psy.commit()
    cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                (input_user_id, 'bot_news', 20))
    conn_psy.commit()

    message_for_admin = 'New user, name: ' + str(input_username) + ' id: ' + str(input_user_id)
    logging.info(message_for_admin)

    return None


def check_if_new_user(input_user_id):
    """check if the user is new or not"""

    global cur
    global conn_psy

    cur.execute("""SELECT user_id FROM users WHERE user_id=%s LIMIT 1;""", (input_user_id,))
    conn_psy.commit()
    info_on_user_from_users = str(cur.fetchone())

    if info_on_user_from_users == 'None':
        user_is_new = True
    else:
        user_is_new = False
        # save_new_user(input_user_id, input_username)

    return user_is_new


# TODO: to be deleted
def save_feedback(func_input):
    global cur
    global conn_psy

    if func_input:
        cur.execute(
            """INSERT INTO feedback (username, feedback_text, feedback_time, user_id, message_id) values 
            (%s, %s, %s, %s, %s);""",
            (func_input[0], func_input[2], func_input[1], func_input[3], func_input[4]))
        conn_psy.commit()

    return None


def save_user_coordinates(input_user_id, input_latitude, input_longitude):
    global cur
    global conn_psy

    cur.execute(
        "DELETE FROM user_coordinates WHERE user_id=%s;", (input_user_id,)
    )
    conn_psy.commit()

    now = datetime.datetime.now()
    cur.execute("""INSERT INTO user_coordinates (user_id, latitude, longitude, upd_time) values (%s, %s, %s, %s);""",
                (input_user_id, input_latitude, input_longitude, now))
    conn_psy.commit()

    return None


def show_user_coordinates(input_user_id):
    global cur
    global conn_psy

    cur.execute("""SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;""",
                (input_user_id,))
    conn_psy.commit()

    # noinspection PyBroadException
    try:
        lat, lon = list(cur.fetchone())
    except Exception:
        lat = None
        lon = None

    return lat, lon


def delete_user_coordinates(input_user_id):
    global cur
    global conn_psy

    cur.execute(
        "DELETE FROM user_coordinates WHERE user_id=%s;", (input_user_id,)
    )
    conn_psy.commit()

    return None


def distance_to_search(search_lat, search_lon, user_let, user_lon):
    import math
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
        points3 = ['&#8593;&#xFE0E;', '&#x2197;&#xFE0F;', '&#8594;&#xFE0E;', '&#8600;&#xFE0E;', '&#8595;&#xFE0E;',
                   '&#8601;&#xFE0E;', '&#8592;&#xFE0E;', '&#8598;&#xFE0E;']

        bearing = calc_bearing(lat_1, lon_1, lat_2, lon_2)
        bearing += 22.5
        bearing = bearing % 360
        bearing = int(bearing / 45)  # values 0 to 7
        nsew = points3[bearing]

        return nsew

    direction = calc_nsew(lat1, lon1, lat2, lon2)

    return [dist, direction]


def get_user_regional_preferences(input_user_id):
    """get user's regional preferences"""

    global cur
    global conn_psy

    user_prefs_list = []

    try:
        cur.execute("SELECT forum_folder_num FROM user_regional_preferences WHERE user_id=%s;", (input_user_id,))
        conn_psy.commit()
        user_reg_prefs_array = cur.fetchall()

        # List of folders not to be shown
        # TODO: to make on SQL level
        no_show = [233, 300, 305, 310]

        for i in range(len(user_reg_prefs_array)):
            temp = user_reg_prefs_array[i]
            if temp[0] not in no_show:
                user_prefs_list.append(temp[0])

        logging.info(str(user_prefs_list))

    except Exception as e:
        logging.info('failed to get user regional prefs')
        logging.exception(e)

    return user_prefs_list


def save_preference(input_user_id, preference):
    global cur
    global conn_psy

    # the mater-table is notif_mailing_types:
    # type_id | type_name
    # 0 | topic_new
    # 1 | topic_status_change
    # 2 | topic_title_change
    # 3 | topic_comment_new
    # 4 | topic_inforg_comment_new
    # 5 | topic_field_trip_new
    # 6 | topic_field_trip_change
    # 20 | bot_news
    # 30 | all
    # 99 | not_defined

    # TODO: make a SQL script to get pref_id
    # TODO: to send pref_id to each update

    # if user wants to have +ALL notifications
    if preference == 'all':
        cur.execute("""DELETE FROM user_preferences WHERE user_id=%s;""", (input_user_id,))
        conn_psy.commit()

        cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                    (input_user_id, preference, 30))
        conn_psy.commit()

    # if user DOESN'T want to have -ALL notifications
    elif preference == '-all':
        cur.execute("""DELETE FROM user_preferences WHERE user_id=%s;""", (input_user_id,))
        conn_psy.commit()

        cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                    (input_user_id, 'bot_news', 20))
        conn_psy.commit()

    # if user wants notifications on NEW SEARCHES or STATUS or TITLE updates
    elif preference in {'new_searches', 'status_changes', 'title_changes'}:

        # Check if there's "ALL" preference
        cur.execute("SELECT id FROM user_preferences WHERE user_id=%s AND preference='all' LIMIT 1;", (input_user_id,))
        conn_psy.commit()
        user_had_all = str(cur.fetchone())

        #
        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR preference='finish' OR 
            preference='all' OR preference=%s);""",
            (input_user_id, preference))
        conn_psy.commit()

        if preference == 'new_searches':
            pref_id = 0
        elif preference == 'status_changes':
            pref_id = 1
        elif preference == 'title_changes':
            pref_id = 2
        else:
            # only for error cases
            pref_id = 99

        cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                    (input_user_id, preference, pref_id))
        conn_psy.commit()

        # Inforg updates handling
        if user_had_all != 'None':
            cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                        (input_user_id, 'bot_news', 20))
            conn_psy.commit()

    # if user DOESN'T want notifications on SPECIFIC updates
    elif preference in {'-new_searches', '-status_changes'}:  # or preference == '-title_changes'
        preference = preference[1:]
        if preference == 'new_searches':
            pref_id = 0
        elif preference == 'status_changes':
            pref_id = 1
        cur.execute("""DELETE FROM user_preferences WHERE user_id = %s AND preference = %s;""",
                    (input_user_id, preference))
        conn_psy.commit()

        cur.execute("SELECT id FROM user_preferences WHERE user_id=%s LIMIT 1;", (input_user_id,))
        conn_psy.commit()
        info_on_user = str(cur.fetchone())

        # TODO: to be substituted with updating the table of user_pref_history
        """if info_on_user == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference) values (%s, %s);",
                        (input_user_id, 'finish'))
            conn_psy.commit()"""

    # if user wants notifications ON COMMENTS
    elif preference == 'comments_changes':

        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR 
            preference='all' OR preference='finish' OR preference='inforg_comments');""",
            (input_user_id,))
        conn_psy.commit()

        cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                    (input_user_id, preference, 3))
        conn_psy.commit()

    # if user DOESN'T want notifications on COMMENTS
    elif preference == '-comments_changes':

        cur.execute("""DELETE FROM user_preferences WHERE user_id = %s AND preference = 'comments_changes';""",
                    (input_user_id,))
        conn_psy.commit()

        cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                    (input_user_id, 'inforg_comments', 4))
        conn_psy.commit()

    # if user wants notifications ON INFORG COMMENTS
    elif preference == 'inforg_comments':

        # Delete Start & Finish
        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR 
            preference='finish' OR preference='inforg_comments');""",
            (input_user_id,))
        conn_psy.commit()

        # Check if ALL of Comments_changes are in place
        cur.execute(
            """SELECT id FROM user_preferences WHERE user_id=%s AND (preference='all' OR 
            preference='comments_changes' OR pref_id=30 OR pref_id=3) LIMIT 1;""",
            (input_user_id,))
        conn_psy.commit()
        info_on_user = str(cur.fetchone())

        # Add Inforg_comments ONLY in there's no ALL or Comments_changes
        if info_on_user == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                        (input_user_id, preference, 4))
            conn_psy.commit()

    # if user DOESN'T want notifications ON INFORG COMMENTS
    elif preference == '-inforg_comments':

        cur.execute("""DELETE FROM user_preferences WHERE user_id = %s AND (preference = 'inforg_comments');""",
                    (input_user_id,))
        conn_psy.commit()

        """cur.execute("SELECT id FROM user_preferences WHERE user_id=%s LIMIT 1;", (input_user_id,))
        conn_psy.commit()
        info_on_user = str(cur.fetchone())

        if info_on_user == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference) values (%s, %s);",
                        (input_user_id, 'finish'))
            conn_psy.commit()"""

    # if user wants notifications ON BOT NEWS
    elif preference == 'bot_news':

        # Delete Start & Finish
        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR 
            preference='finish' OR preference='bot_news');""",
            (input_user_id,))
        conn_psy.commit()

        # Check if ALL is in place
        cur.execute(
            "SELECT id FROM user_preferences WHERE user_id=%s AND (preference='all' OR pref_id=30) LIMIT 1;",
            (input_user_id,))
        conn_psy.commit()
        already_all = str(cur.fetchone())

        # Add Bot_News ONLY in there's no ALL
        if already_all == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                        (input_user_id, preference, 20))
            conn_psy.commit()

    # if user DOESN'T want notifications ON BOT NEWS
    elif preference == '-bot_news':

        cur.execute(
            """DELETE FROM user_preferences WHERE user_id = %s AND (preference = 'bot_news' OR pref_id=20);""",
            (input_user_id,))
        conn_psy.commit()

        """cur.execute("SELECT id FROM user_preferences WHERE user_id=%s LIMIT 1;", (input_user_id,))
        conn_psy.commit()
        info_on_user = str(cur.fetchone())

        if info_on_user == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference) values (%s, %s);",
                        (input_user_id, 'finish'))
            conn_psy.commit()"""

    # if user wants notifications ON FIELD TRIPS
    elif preference == 'new_field_trips':

        # Delete Start & Finish
        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR 
            preference='finish' OR preference='new_field_trips' OR pref_id=5);""",
            (input_user_id,))
        conn_psy.commit()

        # Check if ALL is in place
        cur.execute(
            "SELECT id FROM user_preferences WHERE user_id=%s AND (preference='all' or pref_id=30) LIMIT 1;",
            (input_user_id,))
        conn_psy.commit()
        already_all = str(cur.fetchone())

        # Add new_filed_trips ONLY in there's no ALL
        if already_all == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                        (input_user_id, preference, 5))
            conn_psy.commit()

    # if user DOESN'T want notifications ON FIELD TRIPS
    elif preference == '-new_field_trips':

        cur.execute(
            """DELETE FROM user_preferences WHERE user_id = %s AND (preference = 'new_field_trips' OR pref_id=5);""",
            (input_user_id,))
        conn_psy.commit()

        """cur.execute("SELECT id FROM user_preferences WHERE user_id=%s LIMIT 1;", (input_user_id,))
        conn_psy.commit()
        info_on_user = str(cur.fetchone())

        if info_on_user == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference) values (%s, %s);",
                        (input_user_id, 'finish'))
            conn_psy.commit()"""

    # if user wants notifications ON COORDS CHANGE
    elif preference == 'coords_change':

        # Delete Start & Finish
        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR 
            preference='finish' OR preference='coords_change' OR pref_id=6);""",
            (input_user_id,))
        conn_psy.commit()

        # Check if ALL is in place
        cur.execute(
            "SELECT id FROM user_preferences WHERE user_id=%s AND (preference='all' OR pref_id=30) LIMIT 1;",
            (input_user_id,))
        conn_psy.commit()
        already_all = str(cur.fetchone())

        # Add new_filed_trips ONLY in there's no ALL
        if already_all == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                        (input_user_id, preference, 6))
            conn_psy.commit()

    # if user DOESN'T want notifications ON COORDS CHANGE
    elif preference == '-coords_change':

        cur.execute(
            """DELETE FROM user_preferences WHERE user_id = %s AND (preference = 'coords_change' OR pref_id=6);""",
            (input_user_id,))
        conn_psy.commit()

        """cur.execute("SELECT id FROM user_preferences WHERE user_id=%s LIMIT 1;", (input_user_id,))
        conn_psy.commit()
        info_on_user = str(cur.fetchone())

        if info_on_user == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference) values (%s, %s);",
                        (input_user_id, 'finish'))
            conn_psy.commit()"""

    return None


def update_and_download_list_of_regions(curr_user_id, got_message, com_30, b_fed_dist_pick_other):
    """upload & download the list of user's regions"""

    global cur
    global conn_psy

    msg = ''
    is_first_entry = None
    region_was_in_db = None
    region_is_the_only = None

    fed_okr_dict = {'Дальневосточный ФО',
                    'Приволжский ФО',
                    'Северо-Кавказский ФО',
                    'Северо-Западный ФО'
                    'Сибирский ФО',
                    'Уральский ФО',
                    'Центральный ФО',
                    'Южный ФО'
                    }

    # upload the new regional setting
    reg_dict = {'Москва и МО: Активные Поиски': [276],
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
                'Вологодская обл.': [370, 369, 368],
                'Карелия': [403, 404],
                'Коми': [378, 377, 376],
                'Ленинградская обл.': [120, 300],
                'Мурманская обл.': [214, 372, 373],
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
                'Прочие поиски по СКФО': [184],

                'Прочие поиски по РФ': [116]
                }

    # Reversed dict is needed on the last step
    rev_reg_dict = {value[0]: key for (key, value) in reg_dict.items()}

    # case for the first entry to the screen of Reg Settings
    if got_message == com_30:
        is_first_entry = 'yes'
    elif got_message in fed_okr_dict or got_message == b_fed_dist_pick_other:
        pass
    else:
        try:

            list_of_regs_to_upload = reg_dict[got_message]

            # any region
            cur.execute(
                """SELECT forum_folder_num from user_regional_preferences WHERE user_id=%s;""", (curr_user_id,)
            )
            conn_psy.commit()
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
                        (curr_user_id, region)
                    )
                    conn_psy.commit()

            # Scenario: this setting WAS in place, but now it's the last one - we cannot delete it
            elif region_was_in_db == 'yes' and region_is_the_only:
                pass

            # Scenario: it's a NEW setting, we need to ADD it
            else:
                for region in list_of_regs_to_upload:
                    cur.execute(
                        """INSERT INTO user_regional_preferences (user_id, forum_folder_num) values (%s, %s);""",
                        (curr_user_id, region)
                    )
                    conn_psy.commit()

        except Exception as e:
            logging.info('failed to upload & download the list of user\'s regions')
            logging.exception(e)

    # Get the list of resulting regions
    cur.execute(
        """SELECT forum_folder_num from user_regional_preferences WHERE user_id=%s;""", (curr_user_id,)
    )
    conn_psy.commit()
    user_curr_regs = cur.fetchall()
    user_curr_regs_list = [reg[0] for reg in user_curr_regs]

    for reg in user_curr_regs_list:
        try:
            msg += ',\n &#8226; ' + rev_reg_dict[reg]
        except:  # noqa
            pass

    msg = msg[1:]

    if is_first_entry:
        pre_msg = "Бот может показывать поиски в любом регионе работы ЛА, доступном на форуме.\n"
        pre_msg += "Вы можете подписаться на несколько регионов – просто кликните на соответствующие кнопки регионов." \
                   "\nЧтобы ОТПИСАТЬСЯ от ненужных регионов – нажмите на соответствующую кнопку региона еще раз.\n\n"
        pre_msg += "Текущий список ваших регионов:"
        msg = pre_msg + msg
    elif region_is_the_only:
        msg = 'Необходимо выбрать как минимум один регион. Сейчас выбран' + msg
    elif got_message in fed_okr_dict or got_message == b_fed_dist_pick_other:
        msg = 'Текущий список ваших регионов:' + msg
    else:
        msg = 'Записали. Обновленный список ваших регионов:' + msg

    return msg


def get_last_bot_msg(user_id):
    """get the last bot message to user to define if user is expected to give exact answer"""

    global cur
    global conn_psy

    cur.execute(
        """
        SELECT msg_type FROM msg_from_bot WHERE user_id=%s LIMIT 1;
        """, (user_id,))
    conn_psy.commit()
    extract = cur.fetchone()
    logging.info(f'get the last bot message to user to define if user is expected to give exact answer')
    logging.info(str(extract))

    if extract and extract != 'None':
        msg_type = extract[0]
    else:
        msg_type = None

    logging.info(f'type of the last message from bot: {msg_type}')

    return msg_type


def generate_yandex_maps_place_link(lat, lon, param):
    global coordinates_format

    if param == 'coords':
        display = str(coordinates_format.format(float(lat))) + ', ' + str(coordinates_format.format(float(lon)))
    else:
        display = 'Карта'

    msg = f'<a href="https://yandex.ru/maps/?pt={lon},{lat}&z=11&l=map">{display}</a>'

    return msg


def generate_yandex_maps_route_link(lat1, lon1, lat2, lon2):
    """create a web-link to yandex route from searcher to search"""

    link = '<a href="http://maps.yandex.ru/?rtext=' + str(lat1) + ',' + str(lon1) + '~' + str(lat2) + ',' + str(lon2) \
           + '&rtt=auto">Маршрут</a>'

    return link


def compose_msg_on_reqd_urs_attr(usr_id):
    """get the list of attributes, required for QR code generation"""

    global cur
    global conn_psy

    cur.execute(
        """
        SELECT callsign, region, auto_num, phone, firstname, lastname
        FROM user_attributes WHERE user_id=%s;
        """, (usr_id,)
    )
    conn_psy.commit()
    available_data = list(cur.fetchone())

    msg = ''

    if available_data:
        u_callsign = available_data[0]
        u_region = available_data[1]
        u_auto_num = available_data[2]
        u_phone = available_data[3]
        u_firstname = available_data[4]
        u_lastname = available_data[5]

        if not u_firstname:
            msg += ' &#8226; Ваше имя,\n'
        if not u_lastname:
            msg += ' &#8226; Ваша фамилия,\n'
        if not u_callsign:
            msg += ' &#8226; Позывной,\n'
        if not u_region:
            msg += ' &#8226; Ваш Регион,\n'
        if not u_phone:
            msg += ' &#8226; Номер телефона,\n'
        if not u_auto_num:
            msg += ' &#8226; Гос.номер авто (если есть),\n'

        msg = msg[:-2]

    return msg


def check_and_record_user_attrs(usr_id, user_input):
    """check if user input is inline with requirements and if yes – record them all"""

    global cur
    global conn_psy

    finish_status = False

    cur.execute(
        """
        SELECT callsign, region, auto_num, phone, firstname, lastname
        FROM user_attributes WHERE user_id=%s;
        """, (usr_id,)
    )
    conn_psy.commit()
    available_data = list(cur.fetchone())

    if available_data:
        u_callsign = available_data[0]
        u_region = available_data[1]
        u_auto_num = available_data[2]
        u_phone = available_data[3]
        u_firstname = available_data[4]
        u_lastname = available_data[5]

    number_of_reqd_attr = 0
    list_of_reqd_attr = []

    # TODO: can be simplified with dict & for loop
    if not u_firstname:  # noqa
        number_of_reqd_attr += 1
        list_of_reqd_attr.append('firstname')
    if not u_lastname:  # noqa
        number_of_reqd_attr += 1
        list_of_reqd_attr.append('lastname')
    if not u_callsign:  # noqa
        number_of_reqd_attr += 1
        list_of_reqd_attr.append('callsign')
    if not u_region:  # noqa
        number_of_reqd_attr += 1
        list_of_reqd_attr.append('region')
    if not u_phone:  # noqa
        number_of_reqd_attr += 1
        list_of_reqd_attr.append('phone')
    if not u_auto_num:  # noqa
        number_of_reqd_attr += 1
        list_of_reqd_attr.append('auto_num')

    list_from_user = user_input.split('\n')

    if len(list_from_user) == len(list_of_reqd_attr):

        query = sql.SQL("""
            UPDATE user_attributes SET {}=%s WHERE user_id=%s;
            """)

        for i in range(len(list_from_user)):
            cur.execute(query.format(sql.Identifier(list_of_reqd_attr[i])), [list_from_user[i], usr_id])
            conn_psy.commit()

        finish_status = True

    return finish_status


# TODO: deactivate since Sep 12 2021 – decision not to store QR code images but generate it dynamically
def set_cloud_storage(user_id):
    """sets the basic parameters for connection to txt file in cloud storage, which stores QR codes"""

    bucket_name = 'bucket_for_qr_codes'
    blob_name = str(user_id) + '.png'

    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)

    return blob


# TODO: deactivate since Sep 12 2021 – decision not to store QR code images but generate it dynamically
def write_to_cloud_storage(user_id, what_to_write):
    """writes current searches' snapshot to txt file in cloud storage"""

    blob = set_cloud_storage(user_id)
    blob.upload_from_filename(what_to_write.name, content_type='png')

    return None


# TODO: deactivate since Sep 12 2021 – decision not to store QR code images but generate it dynamically
def read_from_cloud_storage(folder_num):
    """reads previous searches' snapshot from txt file in cloud storage"""

    blob = set_cloud_storage(folder_num)
    contents_as_bytes = blob.download_as_string()
    contents = str(contents_as_bytes, 'utf-8')

    return contents


def generate_text_for_qr_code(user_id):
    """generate text string for further encoding into QR code"""

    global cur
    global conn_psy

    cur.execute(
        """
        SELECT lastname, firstname, callsign, forum_username, region, phone, auto_num 
        FROM user_attributes
        WHERE user_id=%s
        LIMIT 1;
        """, (user_id,)
    )
    conn_psy.commit()
    usr_attrs = list(cur.fetchone())

    line1 = usr_attrs[0] + ' ' + usr_attrs[1] + '\n'
    line2 = usr_attrs[2] + '\n'
    line3 = usr_attrs[3] + '\n'
    line4 = usr_attrs[4] + '\n'
    line5 = usr_attrs[5] + '\n'
    line6 = usr_attrs[6]

    text_string = line1 + line2 + line3 + line4 + line5 + line6

    return text_string


def check_if_ready_for_qr_code(user_id):
    """check if bot has all the necessary info to generate QR code"""

    global cur
    global conn_psy

    verdict = 'good to go'

    cur.execute(
        """
        SELECT lastname, firstname, callsign, forum_username, region, phone, auto_num 
        FROM user_attributes
        WHERE user_id=%s
        LIMIT 1;
        """, (user_id,)
    )
    conn_psy.commit()
    received_data = cur.fetchone()

    # Logic: if all None
    if received_data is None:
        verdict = 'link accounts'
    else:
        usr_attrs = list(received_data)
        for attr in usr_attrs:
            logging.info(f'lets check attr={attr}')
            if attr is None:
                logging.info('attr is None')
                verdict = 'add attrs'
                pass
    logging.info(verdict)

    return verdict


def compose_qr_code(input_data):
    """convert text into picture and save it"""

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=5)
    qr.add_data(input_data)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')

    return img


def prepare_qr_code(user_id):
    """make ALL work from getting data in SQL to prepared picture to be sent to telegram"""

    qr_text = generate_text_for_qr_code(user_id)
    qr_img = compose_qr_code(qr_text)

    bio = BytesIO()
    bio.name = 'image.png'
    qr_img.save(bio, 'PNG')
    bio.seek(0)

    return bio


def get_param_if_exists(upd, func_input):
    """returns either value if exist or None"""

    update = upd  # noqa

    try:
        func_output = eval(func_input)
    except:  # noqa
        func_output = None

    return func_output


def main(request):
    """main function to orchestrate the whole script"""

    # global project_id  # TODO: can be deleted?
    # global client  # TODO: can be deleted?
    global cur
    global conn_psy
    global admin_user_id

    # Set basic params
    bot_token = get_secrets("bot_api_token__prod")
    bot_token_debug = get_secrets("bot_api_token")

    bot = Bot(token=bot_token)
    bot_debug = Bot(token=bot_token_debug)

    admin_user_id = get_secrets("my_telegram_id")
    sql_connect_by_psycopg2()

    bot_request_aft_usr_msg = ''
    msg_sent_by_specific_code = False

    if request.method == "POST":

        update = Update.de_json(request.get_json(force=True), bot)

        logging.info('update: ' + str(update))

        user_new_status = get_param_if_exists(update, 'update.my_chat_member.new_chat_member.status')
        timer_changed = get_param_if_exists(update, 'update.message.message_auto_delete_timer_changed')
        message_id = get_param_if_exists(update, 'update.effective_message.message_id')
        photo = get_param_if_exists(update, 'update.message.photo')
        contact = get_param_if_exists(update, 'update.message.contact')
        inline_query = get_param_if_exists(update, 'update.inline_query')

        channel_type = get_param_if_exists(update, 'update.edited_channel_post.chat.type')
        if not channel_type:
            channel_type = get_param_if_exists(update, 'update.channel_post.chat.type')
        if not channel_type:
            channel_type = get_param_if_exists(update, 'update.my_chat_member.chat.type')

        curr_username = get_param_if_exists(update, 'update.effective_message.from_user.username')

        # TODO: below are chat_id, curr_user_id - but it all the same. to be merged
        curr_user_id = get_param_if_exists(update, 'update.effective_message.from_user.id')
        chat_id = get_param_if_exists(update, 'update.effective_message.chat.id')
        if not chat_id:
            chat_id = get_param_if_exists(update, 'update.edited_channel_post.chat.id')
        if not chat_id:
            chat_id = get_param_if_exists(update, 'update.my_chat_member.chat.id')

        # CASE 1 – when user blocked / unblocked the bot
        if user_new_status in {'kicked', 'member'}:
            try:
                status_dict = {'kicked': 'block_user', 'member': 'unblock_user'}
                # TODO: why redefined the outer scope?
                curr_user_id = update.my_chat_member.chat.id

                # mark user as blocked in psql
                message_for_pubsub = {'action': status_dict[user_new_status], 'info': {'user': curr_user_id}}
                publish_to_pubsub('topic_for_user_management', message_for_pubsub)

                # TODO: in case of unblock – send a message "welcome back, please let us know how to improve?"

            except Exception as e:
                logging.error('Error in finding basic data for block/unblock user in Communicate script: ' + repr(e))
                logging.exception(e)
                pass

        # CASE 2 – when user changed auto-delete setting in the bot
        elif timer_changed:
            logging.info('user changed auto-delete timer settings')

        # CASE 3 – when user sends a PHOTO
        elif photo:
            logging.debug('user sends photos to bot')
            # TODO: it should be avoided for now - but in future we can be able to receive QR codes
            bot.sendMessage(chat_id=chat_id, text='Спасибо, интересное! Только бот не работает с изображениями '
                                                  'и отвечает только на определенные текстовые команды.')

        # CASE 4 – when some Channel writes to bot
        elif channel_type and chat_id < 0:
            bot_debug.sendMessage(chat_id=admin_user_id, text='[Comm]: INFO: CHANNEL sends messages to bot!')

            try:
                bot.leaveChat(chat_id)
                bot_debug.sendMessage(chat_id=admin_user_id, text='[Comm]: INFO: we have left the CHANNEL!')

            except Exception as e:
                logging.error('[Comm]: Leaving channel was not successful:' + repr(e))

        # CASE 5 – when user sends Contact
        elif contact:
            bot.sendMessage(chat_id=chat_id, text='Спасибо, буду знать. Вот только бот не работает с контактами '
                                                  'и отвечает только на определенные текстовые команды.')

        # CASE 6 – when user mentions bot as @LizaAlert_Searcher_Bot in another telegram chat. Bot should do nothing
        elif inline_query:
            bot_debug.sendMessage(chat_id=admin_user_id, text='[comm]: User mentioned bot in some chats')

        # CASE 7 – regular messaging with bot
        else:
            # handling the input messages
            try:
                # TODO: why reassigning the above variables?
                message_id = update.effective_message.message_id
                curr_user_id = update.effective_message.from_user.id
                curr_username = update.effective_message.from_user.username

                logging.info('effective_message: ' + str(update.effective_message))
                logging.info('curr_user_id: ' + str(curr_user_id))

            except Exception as e:
                logging.info('DBG.C.4.ERR: GENERAL COMM CRASH:')
                logging.exception(e)
                logging.error('Error in getting general attributes of the received message in communication script.')

            # check if user is new - and if so - saving him/her
            user_is_new = check_if_new_user(curr_user_id)
            if user_is_new:
                # TODO: to replace with another user_management script?
                save_new_user(curr_user_id, curr_username)

            # get user regional settings (which regions he/she is interested it)
            user_regions = get_user_regional_preferences(curr_user_id)

            # getting message parameters if user send a REPLY to bot message
            reply_to_message_text = ''
            nickname_of_feedback_author = ''
            user_latitude = None
            user_longitude = None
            got_message = None

            try:
                # TODO: to check if this functionality is in use – probably to delete
                if update.effective_message.reply_to_message is not None:
                    reply_to_message_text = str(update.effective_message.reply_to_message.text)
                    nickname_of_feedback_author = str(update.effective_message.reply_to_message.chat.username)
                    feedback_time = update.effective_message.reply_to_message.date
                    feedback_from_user = update.effective_message.text

                if update.effective_message.location is not None:
                    user_latitude = update.effective_message.location.latitude
                    user_longitude = update.effective_message.location.longitude

                if update.effective_message.text is not None:
                    got_message = update.effective_message.text

            except Exception as e:
                logging.info('DBG.C.2.ERR: GENERAL COMM CRASH:')
                logging.exception(e)

            # to avoid errors
            bot_message = ''

            # Buttons & Keyboards
            # Start & Main menu
            b_start = '/start'
            com_2 = 'посмотреть актуальные поиски'
            com_27 = 'настроить бот'
            b_gen_qr = 'получить QR-код'
            b_other = 'другие возможности'
            keyboard_main = [[com_2], [com_27], [b_other]]  # [[com_2], [com_27], [b_gen_qr], [b_other]]
            reply_markup_main = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)

            # Settings menu
            com_3 = 'настроить уведомления'
            b_settings_coords = 'настроить "домашние координаты"'
            b_back_to_start = 'в начало'

            # Settings - notifications
            com_4 = 'включить: все уведомления'
            com_5 = 'включить: о новых поисках'
            com_6 = 'включить: об изменениях статусов'
            com_7 = 'включить: о всех новых комментариях'
            b_act_inforg_com = 'включить: о комментариях Инфорга'
            b_act_new_filed_trip = 'включить: о новых выездах'
            b_act_coords_change = 'включить: о смене места штаба'
            com_9 = 'включить: о новых функциях бота'
            com_15 = 'отключить и настроить более гибко'
            com_16 = 'отключить: о новых поисках'
            com_17 = 'отключить: об изменениях статусов'
            com_18 = 'отключить: о всех новых комментариях'
            b_deact_inforg_com = 'отключить: о комментариях Инфорга'
            b_deact_new_filed_trip = 'отключить: о новых выездах'
            b_deact_coords_change = 'отключить: о смене места штаба'
            com_12 = 'отключить: о новых функциях бота'
            # TODO: experiment
            # com_yy = 'включить: об изменении списка задач по поиску'
            # com_xx = 'отключить: об изменении списка задач по поиску'
            # com_40 = 'включить: о ключевых изменениях по поискам'
            # com_41 = 'отключить: о ключевых изменениях по поискам'
            # com_25 = 'включить: статистика за прошедшую неделю'
            # com_26 = 'отключить: статистика за прошедшую неделю'

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
            # b_fed_dist_belarus = 'Беларусь'
            # b_fed_dist_kazakhs = 'Казахстан'
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
                                     # [b_fed_dist_belarus],
                                     # [b_fed_dist_kazakhs],
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
            b_reg_sev_kav_other = 'Прочие поиски по СКФО'
            keyboard_sev_kav_reg_choice = [[b_reg_dagestan],
                                           [b_reg_stavropol],
                                           [b_reg_chechnya],
                                           [b_reg_kabarda],
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
            b_reg_sev_zap_other = 'Все остальные в СЗФО'
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
            com_30 = 'настроить регион поисков'

            full_list_of_regions = keyboard_dal_vost_reg_choice[:-1] + keyboard_privolz_reg_choice[:-1] \
                + keyboard_sev_kav_reg_choice[:-1] + keyboard_sev_zap_reg_choice[:-1] \
                + keyboard_sibiria_reg_choice[:-1] + keyboard_urals_reg_choice[:-1] \
                + keyboard_central_reg_choice[:-1] + keyboard_yuzhniy_reg_choice[:-1] \
                + [[b_fed_dist_other_r]]
            full_dict_of_regions = {word[0] for word in full_list_of_regions}

            dict_of_fed_dist = {b_fed_dist_dal_vos: keyboard_dal_vost_reg_choice,
                                b_fed_dist_privolz: keyboard_privolz_reg_choice,
                                b_fed_dist_sev_kaz: keyboard_sev_kav_reg_choice,
                                b_fed_dist_sev_zap: keyboard_sev_zap_reg_choice,
                                b_fed_dist_sibiria: keyboard_sibiria_reg_choice,
                                b_fed_dist_uralsky: keyboard_urals_reg_choice,
                                b_fed_dist_central: keyboard_central_reg_choice,
                                b_fed_dist_yuzhniy: keyboard_yuzhniy_reg_choice  # ,
                                # b_fed_dist_other_r: keyboard_fed_dist_set
                                }

            # Feedback
            text_of_feedback_request = 'Если у вас есть комментарии или пожелания по работе бота, ' \
                                       'отправьте их разработчику обратным сообщением с цитированием. \n' \
                                       'Если вы отключите цитирование этого сообщения и отправите что-либо ' \
                                       'боту – ваше сообщение не будет сохранено, а вы вернетесь на начальный экран'
            reply_markup_feedback_reply = ForceReply(force_reply=True, seletive=False)

            # Forum actions
            b_yes_its_me = 'да, это я'
            b_no_its_not_me = 'нет, это не я'

            # Other menu
            com_1 = 'посмотреть последние поиски'
            b_send_feedback = 'написать разработчику бота - старое'
            b_goto_community = 'написать разработчику бота'
            b_goto_first_search = 'полезная информация для новичка'
            keyboard_other = [[com_1], [b_goto_first_search],
                              [b_goto_community], [b_back_to_start]]

            # Admin - specially keep it for Admin, regular users unlikely will be interested in it

            com_10 = 'названия'  # these are "Title update notification" button

            b_admin_menu = 'admin'
            b_test_menu = 'test'
            # b_prep_for_qr = 'настроить бот и получить QR-код' - OUTDATED
            b_link_to_forum = 'связать аккаунты бота и форума'
            b_add_usr_attr_menu = 'ввести требуемые параметры'

            # basic markup which will be substituted for all specific cases
            reply_markup = reply_markup_main

            # Check what was last request from bot and if bot is expecting user's input
            bot_request_bfr_usr_msg = get_last_bot_msg(curr_user_id)

            if bot_request_bfr_usr_msg:
                logging.info(f'bore this message bot was waiting for {bot_request_bfr_usr_msg} '
                             f'from user {curr_user_id}')
            else:
                logging.info(f'bore this message bot was NOT waiting anything from user {curr_user_id}')

            try:
                # get coordinates from the text
                if bot_request_bfr_usr_msg == 'input_of_coords_man':

                    # TODO: in case if user sends the Photo instead of coordinates – script is falling. can be
                    #  assumed later
                    # Check if user input is in format of coordinates
                    # noinspection PyBroadException
                    try:
                        numbers = [float(s) for s in re.findall(r'-?\d+\.?\d*', got_message)]
                        if numbers and len(numbers) > 1 and 30 < numbers[0] < 80 and 10 < numbers[1] < 190:
                            user_latitude = numbers[0]
                            user_longitude = numbers[1]
                    except Exception:
                        pass

                # if there is any message text from user
                if user_latitude or got_message:

                    # if there are user's coordinates in the message
                    if user_latitude:

                        save_user_coordinates(curr_user_id, user_latitude, user_longitude)
                        bot_message = 'Ваши "домашние координаты" сохранены:\n'
                        bot_message += generate_yandex_maps_place_link(user_latitude, user_longitude, 'coords')
                        bot_message += '\nТеперь для всех поисков, где удастся распознать координаты штаба или ' \
                                       'населенного пункта, будет указываться направление и расстояние по прямой от ' \
                                       'ваших "домашних координат".'

                        keyboard_settings = [[b_coords_auto_def], [b_coords_man_def], [b_coords_check], [b_coords_del],
                                             [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard_settings, resize_keyboard=True)

                        bot.sendMessage(chat_id=chat_id, text=bot_message, reply_markup=reply_markup, parse_mode='HTML',
                                        disable_web_page_preview=True)
                        msg_sent_by_specific_code = True

                        # saving the last message from bot
                        if not bot_request_aft_usr_msg:
                            bot_request_aft_usr_msg = 'not_defined'

                        try:
                            cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (curr_user_id,))
                            conn_psy.commit()

                            cur.execute(
                                """
                                INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);
                                """,
                                (curr_user_id, datetime.datetime.now(), bot_request_aft_usr_msg))
                            conn_psy.commit()

                        except Exception as e:
                            logging.info('failed to update the last saved message from bot')
                            logging.exception(e)

                    # Send summaries
                    elif got_message in {com_1, com_2}:

                        msg_sent_by_specific_code = True

                        temp_dict = {com_1: 'all', com_2: 'active'}

                        cur.execute(
                            """
                            select forum_folder_id, folder_description from regions_to_folders;
                            """
                        )
                        conn_psy.commit()
                        regions_table = cur.fetchall()

                        region_name = ''
                        for region in user_regions:
                            for line in regions_table:

                                if line[0] == region:
                                    region_name = line[1]
                                    break

                            # check if region – is an archive folder: if so – it can be sent only to 'all'
                            if region_name.find('аверш') == -1 or temp_dict[got_message] == 'all':

                                bot_message = send_a_list_of_searches(temp_dict[got_message], curr_user_id,
                                                                      region, region_name)
                                reply_markup = reply_markup_main

                                bot.sendMessage(chat_id=chat_id, text=bot_message, reply_markup=reply_markup,
                                                parse_mode='HTML', disable_web_page_preview=True)

                                # saving the last message from bot
                                try:
                                    cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (curr_user_id,))
                                    conn_psy.commit()

                                    cur.execute(
                                        """
                                        INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);
                                        """,
                                        (curr_user_id, datetime.datetime.now(), 'report'))
                                    conn_psy.commit()

                                except Exception as e:
                                    logging.info('failed to save the last message from bot')
                                    logging.exception(e)

                    # Perform individual replies

                    # Admin mode
                    elif got_message.lower() == b_admin_menu:
                        bot_message = "Вы вошли в специальный тестовый админ-раздел"

                        # keyboard for Home Coordinates sharing
                        keyboard_coordinates_admin = [[b_link_to_forum], [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

                    # Test mode
                    elif got_message.lower() == b_test_menu:
                        bot_message = 'Вы вошли в специальный тестовый раздел, здесь доступны функции в стадии ' \
                                      'отладки и тестирования. Представленный здесь функционал может не работать ' \
                                      'на 100% корректно. Если заметите случаи некорректного выполнения функционала' \
                                      ' из этого раздела – пишите, пожалуйста, в телеграм-чат ' \
                                      'https://t.me/joinchat/2J-kV0GaCgwxY2Ni'
                        keyboard_coordinates_admin = [[b_act_new_filed_trip], [b_deact_new_filed_trip],
                                                      [b_act_coords_change], [b_deact_coords_change], [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

                    # If user Region is Moscow or not
                    elif got_message == b_reg_moscow:
                        bot_message = 'Спасибо, бот запомнил этот выбор и теперь вы сможете получать ключевые ' \
                                      'уведомления в регионе Москва и МО. Вы в любой момент сможете изменить список ' \
                                      'регионов через настройки бота.'
                        reply_markup = reply_markup_main

                        if user_is_new:
                            # add the New User into table user_regional_preferences
                            # region is Moscow for Active Searches & InfoPod
                            cur.execute(
                                """INSERT INTO user_regional_preferences (user_id, forum_folder_num) values 
                                (%s, %s);""",
                                (curr_user_id, 276))
                            conn_psy.commit()
                            cur.execute(
                                """INSERT INTO user_regional_preferences (user_id, forum_folder_num) values 
                                (%s, %s);""",
                                (curr_user_id, 41))
                            conn_psy.commit()

                    elif got_message == b_reg_not_moscow:
                        bot_message = 'Спасибо, тогда, пожалуйста, выберите хотя бы один регион поисков, ' \
                                      'чтобы начать получать уведомления. Вы в любой момент сможете изменить список ' \
                                      'регионов через настройки бота.'
                        keyboard = [[com_30], [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                    # TODO: not in use right now (after QR codes deprecation)
                    elif got_message == b_link_to_forum:
                        bot_message = 'Чтобы связать бота с вашим аккаунтом, введите ответным сообщением ваше ' \
                                      'Имя Пользователя на форуме (логин). Желательно даже скопировать имя ' \
                                      'с форума, чтобы избежать ошибок.'
                        keyboard = [[b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                        bot_request_aft_usr_msg = 'input_of_forum_username'

                    elif bot_request_bfr_usr_msg == 'input_of_forum_username' \
                            and got_message not in {b_admin_menu, b_back_to_start, b_test_menu} \
                            and len(got_message.split()) < 4:
                        message_for_pubsub = [curr_user_id, got_message]
                        publish_to_pubsub('parse_user_profile_from_forum', message_for_pubsub)
                        bot_message = 'Сейчас посмотрю, это может занять до 10 секунд...'
                        keyboard = [[b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                    elif got_message in {b_yes_its_me, b_add_usr_attr_menu}:

                        # Write "verified" for user
                        cur.execute("""UPDATE user_forum_attributes SET status='verified' 
                        WHERE user_id=%s and timestamp = 
                        (SELECT MAX(timestamp) FROM user_forum_attributes WHERE user_id=%s);""",
                                    (curr_user_id, curr_user_id))
                        conn_psy.commit()

                        # Delete prev record in user_attributes
                        cur.execute("""DELETE FROM user_attributes  
                        WHERe user_id=%s;""", (curr_user_id,))
                        conn_psy.commit()

                        # Copy verified QR-related data to static table
                        cur.execute("""
                                    INSERT INTO user_attributes (user_id, forum_user_id, forum_username, callsign, 
                                    region, auto_num, phone)
                                    (SELECT user_id, forum_user_id, forum_username, forum_callsign, forum_region, 
                                    forum_auto_num, forum_phone FROM user_forum_attributes 
                                    WHERE user_id=%s AND timestamp = (
                                    SELECT MAX(timestamp) FROM user_forum_attributes 
                                    WHERE user_id=%s and status='verified'));
                                    """, (curr_user_id, curr_user_id))
                        conn_psy.commit()

                        bot_message = 'Отлично, мы записали: теперь бот будет понимать, кто вы на форуме.\n' \
                                      'Теперь для генерации QR-кода, пожалуйста, вышлите ваши параметры ' \
                                      'в теле одного сообщения: по одному в каждой ' \
                                      'строчке. Получается, что сколько параметров вам нужно ввести, столько строк ' \
                                      'и будет в вашем единственном сообщении. Если у нас нет позывного или авто, ' \
                                      'на котором вы ездите на поиски, просто поставьте прочерки в ' \
                                      'соответствующих строках.\nИтак, отправьте в сообщении, п-та:\n'
                        bot_message += compose_msg_on_reqd_urs_attr(curr_user_id)
                        keyboard = [[b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                        bot_request_aft_usr_msg = 'addl_attrs_for_qr'

                    elif got_message == b_no_its_not_me:
                        bot_message = 'Пожалуйста, тщательно проверьте написание вашего ника на форуме ' \
                                      '(кириллица/латиница, без пробела в конце) и введите его заново'
                        keyboard = [[b_link_to_forum], [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                        bot_request_aft_usr_msg = 'input_of_forum_username'

                    elif bot_request_bfr_usr_msg == 'addl_attrs_for_qr' and got_message \
                            and got_message not in {b_back_to_start}:

                        result = check_and_record_user_attrs(curr_user_id, got_message)

                        if result:
                            bot_message = 'Супер! Теперь ваш QR код всегда в доступе: его можно либо открывать ' \
                                          'из истории изображений от бота в телеграм, либо в нужный момент ' \
                                          'его можно скачать заново (для работы бота требуется интернет)'
                            keyboard = [[b_back_to_start]]
                            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                            bot.sendMessage(chat_id=chat_id, text=bot_message, reply_markup=reply_markup,
                                            parse_mode='HTML', disable_web_page_preview=True)

                            qr_picture = prepare_qr_code(curr_user_id)
                            reply_markup = reply_markup_main
                            bot.sendPhoto(chat_id=chat_id, photo=qr_picture, reply_markup=reply_markup)

                            msg_sent_by_specific_code = True

                        else:
                            bot_message = 'к сожалению, что-то пошло не так. Пожалуйста, попробуйте еще раз ' \
                                          'ввести дополнительные параметры'
                            keyboard = [[b_add_usr_attr_menu], [b_back_to_start]]
                            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                    # TODO: for debugging purposes only
                    elif got_message.lower() == 'go':
                        publish_to_pubsub('topic_notify_admin', 'test_admin_check')

                    elif got_message == b_gen_qr:

                        qr_status = check_if_ready_for_qr_code(curr_user_id)

                        if qr_status == 'good to go':

                            qr_picture = prepare_qr_code(curr_user_id)
                            reply_markup = reply_markup_main
                            bot.sendPhoto(chat_id=chat_id, photo=qr_picture, reply_markup=reply_markup)
                            msg_sent_by_specific_code = True

                        elif qr_status == 'add attrs':
                            bot_message = 'Для генерации QR-кода не хватает некоторых ваших данных.\n' \
                                          'Пожалуйста, вышлите ваши параметры ' \
                                          'в теле сообщения: по одному в каждой ' \
                                          'строчке. Получается, что сколько параметров вам нужно ввести, столько ' \
                                          'строк ' \
                                          'и будет в вашем сообщении. Если у нас нет позывного или авто, ' \
                                          'на котором вы ездите на поиски, обязательно поставьте прочерки в ' \
                                          'соответствующих строках\n Итак, отправьте в сообщении п-та:\n'
                            bot_message += compose_msg_on_reqd_urs_attr(curr_user_id)
                            keyboard = [[b_back_to_start]]
                            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                            bot_request_aft_usr_msg = 'addl_attrs_for_qr'

                        elif qr_status == 'link accounts':
                            bot_message = 'Иметь QR под рукой в Боте гораздо удобнее, чем каждый раз открывать ' \
                                          'разделы ' \
                                          'форума или искать в сохраненных файлах. Однако, чтобы Бот смог получить ' \
                                          'QR-код, необходимо пройти 2 простых шага:\n 1. Связать свой аккаунт ' \
                                          'телеграм и аккаунт на форуме. Для этого нужно просто указать своё имя ' \
                                          'пользователя на форуме.\n 2. Далее ввести дополнительные данные, если ' \
                                          'их не ' \
                                          'будет на форуме.\n На основе этого бот автоматически сгенерирует ваш ' \
                                          'QR-код, который ' \
                                          'теперь всегда будет доступен в боте за пару кликов. Также, если однажды ' \
                                          'запросить бота сгенерировать QR код – он может храниться в истории ' \
                                          'Телеграм и быть всегда под рукой.'
                            keyboard = [[b_link_to_forum], [b_back_to_start]]
                            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                    elif got_message == b_other:
                        bot_message = 'Здесь можно посмотреть статистику по 20 последним поискам, перейти в ' \
                                      'канал Коммъюнити или Прочитать важную информацию для Новичка'
                        reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

                    elif got_message in {com_30, b_fed_dist_pick_other}:
                        bot_message = update_and_download_list_of_regions(curr_user_id, got_message, com_30,
                                                                          b_fed_dist_pick_other)
                        reply_markup = ReplyKeyboardMarkup(keyboard_fed_dist_set, resize_keyboard=True)

                    # elif got_message == b_fed_dist_pick_other:
                    #    bot_message =
                    #    reply_markup = ReplyKeyboardMarkup(keyboard_fed_dist_set, resize_keyboard=True)

                    elif got_message in dict_of_fed_dist:
                        updated_regions = update_and_download_list_of_regions(curr_user_id, got_message, com_30,
                                                                              b_fed_dist_pick_other)
                        bot_message = updated_regions
                        reply_markup = ReplyKeyboardMarkup(dict_of_fed_dist[got_message], resize_keyboard=True)

                    elif got_message in full_dict_of_regions:
                        updated_regions = update_and_download_list_of_regions(curr_user_id, got_message, com_30,
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

                    elif got_message == com_27:
                        bot_message = 'Это раздел с настройками. Здесь вы можете выбрать удобные для вас ' \
                                      'уведомления, а также ввести свои "домашние координаты", на основе которых ' \
                                      'будет рассчитываться расстояние и направление до места поиска. Вы в любой ' \
                                      'момент сможете изменить эти настройки.'
                        keyboard_settings = [[com_30], [b_settings_coords], [com_3], [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard_settings, resize_keyboard=True)

                    elif got_message == b_settings_coords:
                        bot_message = 'Нажмите на кнопку и разрешите определить вашу текущую геопозицию или ' \
                                      'введите ее вручную, чтобы бот смог запомнить ее. Далее эти координаты ' \
                                      'будут считаться вашим "домом", откуда будем рассчитывать расстояние и ' \
                                      'направление до поисков. Автоматическое определение координат работает ' \
                                      'только для носимых устройств с функцией GPS, для Настольных ПК ' \
                                      'используйте, пожалуйста, ручной ввод.'
                        keyboard_coordinates_1 = [[b_coords_auto_def], [b_coords_man_def], [b_coords_check],
                                                  [b_coords_del], [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

                    elif got_message == b_coords_del:
                        delete_user_coordinates(curr_user_id)
                        bot_message = 'Ваши "домашние координаты" удалены. Теперь расстояние и направление ' \
                                      'до поисков не будет отображаться.'
                        keyboard_coordinates_1 = [[b_coords_auto_def], [b_coords_man_def], [b_coords_check],
                                                  [b_coords_del], [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

                    elif got_message == b_coords_man_def:
                        bot_message = 'Введите координаты вашего дома вручную в теле сообщения и просто ' \
                                      'отправьте. Формат: XX.XXX, XX.XXX, где количество цифр после точки ' \
                                      'может быть различным. Широта должна быть между 30.0 и 80.0 градусами, ' \
                                      'Долгота – между 10.0 и 190.0 градусами.'
                        bot_request_aft_usr_msg = 'input_of_coords_man'
                        keyboard_coordinates_1 = [[b_coords_auto_def], [b_coords_man_def], [b_coords_check],
                                                  [b_coords_del], [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

                    elif got_message == b_coords_check:

                        lat, lon = show_user_coordinates(curr_user_id)
                        if lat and lon:
                            bot_message = 'Ваши "домашние координаты" '
                            bot_message += generate_yandex_maps_place_link(lat, lon, 'coords')

                        else:
                            bot_message = 'Ваши координаты пока не сохранены. Введите их автоматически или вручную.'

                        keyboard_coordinates_1 = [[b_coords_auto_def], [b_coords_man_def],
                                                  [b_coords_check], [b_coords_del], [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

                    elif got_message == b_start:

                        if user_is_new:
                            bot_message = 'Привет! Бот управляется кнопками, которые заменяют обычную клавиатуру.' \
                                          '\n\nУточните пожалуйста, Москва и Моск. Область – это ' \
                                          'ваш основной регион поисков?'
                            keyboard_coordinates_admin = [[b_reg_moscow], [b_reg_not_moscow]]
                            reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

                        else:
                            bot_message = 'Привет! Бот управляется кнопками, которые заменяют обычную клавиатуру.'
                            reply_markup = reply_markup_main

                    # TODO: to be deprecated
                    elif got_message == b_send_feedback:
                        bot_message = text_of_feedback_request
                        reply_markup = reply_markup_feedback_reply

                    elif reply_to_message_text == text_of_feedback_request:
                        combined_feedback = [nickname_of_feedback_author, feedback_time, feedback_from_user,
                                             curr_user_id, message_id]
                        save_feedback(combined_feedback)
                        bot_message = 'Спасибо за обратную связь, она помогает делать работу поисковиков ' \
                                      'ЛА удобнее!'
                        reply_markup = reply_markup_main

                    elif got_message == b_back_to_start:
                        bot_message = 'возвращаемся в главное меню'
                        reply_markup = reply_markup_main

                    # save preference for -ALL
                    elif got_message == com_15:
                        bot_message = 'Уведомления отключены. Кстати, их можно настроить более гибко'
                        save_preference(curr_user_id, '-all')
                        keyboard_notifications_all_quit = [[com_4], [com_5], [com_6], [com_7], [com_12],
                                                           [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard_notifications_all_quit, resize_keyboard=True)

                    # save preference for +ALL
                    elif got_message == com_4:
                        bot_message = 'Супер! теперь вы будете получать уведомления в телеграм в случаях: ' \
                                      'появление нового поиска, изменение статуса поиска (стоп, НЖ, НП), ' \
                                      'появление новых комментариев по всем поискам. Вы в любой момент можете ' \
                                      'изменить список уведомлений'
                        save_preference(curr_user_id, 'all')
                        keyboard_notifications_all_quit = [[com_15], [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard_notifications_all_quit, resize_keyboard=True)

                    elif got_message == b_goto_community:
                        bot_message = 'Бот можно обсудить с соотрядниками в ' \
                                      '<a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальном Чате ' \
                                      'в телеграм</a>. Там можно предложить свои идеи, указать на проблемы ' \
                                      'и получить быструю обратную связь от разработчика.'
                        keyboard_other = [[com_1], [b_goto_community], [b_goto_first_search], [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

                    elif got_message == b_goto_first_search:
                        bot_message = 'Если вы новичок и у вас за плечами не так много поисков – приглашаем ' \
                                      '<a href="https://xn--b1afkdgwddgp9h.xn--p1ai/">ознакомиться с основами ' \
                                      'работы ЛА</a>. Всю теорию работы ЛА необходимо получать от специально ' \
                                      'обученных волонтеров ЛА. Но если у вас еще не было возможности пройти ' \
                                      'официальное обучение, а вы уже готовы выехать на поиск – этот ресурс для вас.'
                        keyboard_other = [[com_1], [b_goto_community], [b_goto_first_search], [b_back_to_start]]
                        reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

                    # special block for flexible menu on notification preferences
                    elif got_message in {com_5, com_6, com_10, com_7, com_3, com_17, com_18, com_16, com_9, com_12,
                                         b_act_inforg_com, b_deact_inforg_com,
                                         b_act_new_filed_trip, b_deact_new_filed_trip,
                                         b_act_coords_change, b_deact_coords_change}:

                        # save preference for +NEW SEARCHES
                        if got_message == com_5:
                            bot_message = 'Отлично! Теперь вы будете получать уведомления в телеграм при ' \
                                          'появлении нового поиска. Вы в любой момент можете изменить ' \
                                          'список уведомлений'
                            save_preference(curr_user_id, 'new_searches')

                        # save preference for -NEW SEARCHES
                        elif got_message == com_16:
                            bot_message = 'Записали'
                            save_preference(curr_user_id, '-new_searches')

                        # save preference for +BotNews
                        elif got_message == com_9:
                            bot_message = 'Теперь в случае появления нового функционала бота вы узнаете об этом в ' \
                                          'небольшом новостном сообщении'
                            save_preference(curr_user_id, 'bot_news')

                        # save preference for -BotNews
                        elif got_message == com_12:
                            bot_message = 'Вы отписались от уведомлений по новому функционалу бота. Когда появится ' \
                                          'какая-либо новая функция - бот, к сожалению, не сможет вам об этом сообщить.'
                            save_preference(curr_user_id, '-bot_news')

                        # save preference for +STATUS UPDATES
                        elif got_message == com_6:
                            bot_message = 'Отлично! теперь вы будете получать уведомления в телеграм при изменении ' \
                                          'статуса поисков (НЖ, НП, СТОП и т.п.). Вы в любой момент можете изменить ' \
                                          'список уведомлений'
                            save_preference(curr_user_id, 'status_changes')

                        # save preference for -STATUS UPDATES
                        elif got_message == com_17:
                            bot_message = 'Записали'
                            save_preference(curr_user_id, '-status_changes')

                        # save preference for TITLE UPDATES
                        elif got_message == com_10:
                            bot_message = 'Отлично!'
                            save_preference(curr_user_id, 'title_changes')

                        # save preference for +COMMENTS
                        elif got_message == com_7:
                            bot_message = 'Отлично! Теперь все новые комментарии будут у вас! Вы в любой момент ' \
                                          'можете изменить список уведомлений'
                            save_preference(curr_user_id, 'comments_changes')

                        # save preference for -COMMENTS
                        elif got_message == com_18:
                            bot_message = 'Записали. Мы только оставили вам включенными уведомления о комментариях ' \
                                          'Инфорга. Их тоже можно отключить'
                            save_preference(curr_user_id, '-comments_changes')

                        # save preference for +InforgComments
                        elif got_message == b_act_inforg_com:
                            bot_message = 'Если вы не подписаны на уведомления по всем комментариям, то теперь ' \
                                          'вы будете получать уведомления о комментариях от Инфорга. Если же вы ' \
                                          'уже подписаны на все комментарии – то всё остаётся без изменений: бот ' \
                                          'уведомит вас по всем комментариям, включая от Инфорга'
                            save_preference(curr_user_id, 'inforg_comments')

                        # save preference for -InforgComments
                        elif got_message == b_deact_inforg_com:
                            bot_message = 'Вы отписались от уведомлений по новым комментариям от Инфорга'
                            save_preference(curr_user_id, '-inforg_comments')

                        # save preference for +NewFieldTrips
                        elif got_message == b_act_new_filed_trip:
                            bot_message = 'Теперь вы будете получать уведомления о новых выездах по уже идущим ' \
                                          'поискам. Обратите внимание, что это не рассылка по новым темам на форуме, ' \
                                          'а именно о том, что в существующей теме в ПЕРВОМ посте появилась ' \
                                          'информация о новом выезде'
                            save_preference(curr_user_id, 'new_field_trips')

                        # save preference for -NewFieldTrips
                        elif got_message == b_deact_new_filed_trip:
                            bot_message = 'Вы отписались от уведомлений по новым выездам'
                            save_preference(curr_user_id, '-new_field_trips')

                        # save preference for +CoordsChange
                        elif got_message == b_act_coords_change:
                            bot_message = 'Если у штаба поменяются координаты (и об этом будет написано в первом ' \
                                          'посте на форуме) – бот уведомит вас об этом'
                            save_preference(curr_user_id, 'coords_change')

                        # save preference for -CoordsChange
                        elif got_message == b_deact_coords_change:
                            bot_message = 'Вы отписались от уведомлений о смене места (координат) штаба'
                            save_preference(curr_user_id, '-coords_change')

                        # GET what are preferences
                        elif got_message == com_3:
                            prefs = send_user_preferences(curr_user_id)
                            if prefs[0] == 'пока нет включенных уведомлений' or prefs[0] == 'неизвестная настройка':
                                bot_message = 'Выберите, какие уведомления вы бы хотели получать'
                            else:
                                bot_message = 'Сейчас у вас включены следующие виды уведомлений:\n'
                                bot_message += prefs[0]

                        else:
                            bot_message = 'empty message'
                            reply_markup = reply_markup_main

                        # getting the list of user notification preferences
                        prefs = send_user_preferences(curr_user_id)
                        keyboard_notifications_flexible = [[com_4], [com_5], [com_6], [com_7], [b_act_inforg_com],
                                                           [com_9], [b_back_to_start]]
                        # just a comparison with negative [[com_15],[com_16],[com_17],[com_18],[b_deact_inforg_com],
                        #                                  [com_12],[b_back_to_start]]

                        for i in range(len(prefs[1])):
                            if prefs[1][i] == 'all':
                                keyboard_notifications_flexible = [[com_15], [b_back_to_start]]
                            elif prefs[1][i] == 'new_searches':
                                keyboard_notifications_flexible[1] = [com_16]
                            elif prefs[1][i] == 'status_changes':
                                keyboard_notifications_flexible[2] = [com_17]
                            elif prefs[1][i] == 'comments_changes':
                                keyboard_notifications_flexible[3] = [com_18]
                            elif prefs[1][i] == 'inforg_comments':
                                keyboard_notifications_flexible[4] = [b_deact_inforg_com]
                            elif prefs[1][i] == 'bot_news':
                                keyboard_notifications_flexible[5] = [com_12]

                        reply_markup = ReplyKeyboardMarkup(keyboard_notifications_flexible, resize_keyboard=True)

                    # in case of other user messages:
                    else:
                        # If command in unknown
                        bot_message = 'не понимаю такой команды, пожалуйста, используйте кнопки со стандартными ' \
                                      'командами ниже'
                        bot_message += reply_to_message_text
                        reply_markup = reply_markup_main

                    if not msg_sent_by_specific_code:
                        bot.sendMessage(chat_id=chat_id, text=bot_message, reply_markup=reply_markup,
                                        parse_mode='HTML', disable_web_page_preview=True)

                    # saving the last message from bot
                    if not bot_request_aft_usr_msg:
                        bot_request_aft_usr_msg = 'not_defined'

                    try:
                        cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (curr_user_id,))
                        conn_psy.commit()

                        cur.execute(
                            """
                            INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);
                            """,
                            (curr_user_id, datetime.datetime.now(), bot_request_aft_usr_msg))
                        conn_psy.commit()
                    except Exception as e1:
                        logging.info('DBG.C.50.EXC:')
                        logging.exception(e1)

                else:
                    logging.info('DBG.C.6. THERE IS a COMM SCRIPT INVOCATION w/O MESSAGE OR COORDINATES:')
                    logging.info(str(update))
                    text_for_admin = 'Пустое сообщение в скрипте Communicate: '
                    try:
                        text_for_admin += str(curr_user_id) + ', ' + str(curr_username) + ', '
                    except: # noqa
                        pass
                    try:
                        text_for_admin += str(got_message) + ', '
                    except: # noqa
                        pass
                    try:
                        text_for_admin += str(update.effective_message) + ', '
                    except: # noqa
                        pass
                    try:
                        text_for_admin += bot_request_bfr_usr_msg
                    except: # noqa
                        pass
                    bot_debug.sendMessage(chat_id=admin_user_id, text=text_for_admin,
                                          reply_markup=reply_markup, parse_mode='HTML')

            except Exception as e:
                logging.error('DBG.C.0.ERR: GENERAL COMM CRASH: ' + repr(e))
                logging.exception(e)
                bot_debug.sendMessage(chat_id=admin_user_id, text=('Упал скрипт Communicate0:' + str(e)),
                                      parse_mode='HTML')

    cur.close()
    conn_psy.close()

    return None
