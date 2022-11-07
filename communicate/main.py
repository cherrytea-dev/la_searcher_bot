"""receive telegram messages from users to bot, act accordingly and send back the reply"""

import os
import datetime
import re
import json
import logging
import math
import psycopg2

from telegram import ReplyKeyboardMarkup, ForceReply, KeyboardButton, Bot, Update

from google.cloud import secretmanager, pubsub_v1, storage


publisher = pubsub_v1.PublisherClient()
project_id = os.environ["GCP_PROJECT"]
client = secretmanager.SecretManagerServiceClient()

# To get rid of telegram "Retrying" Warning logs, which are shown in GCP Log Explorer as Errors.
# Important – these are not errors, but jest informational warnings that there were retries, that's why we exclude them
logging.getLogger("telegram.vendor.ptb_urllib3.urllib3").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


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
        logging.info('Pub/sub message was published')

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

    # first_word_parameter = 'Ищем '
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


def compose_user_preferences_message(conn_psy, cur, user_id):
    """Compose a text for user on which types of notifications are enabled for zir"""

    cur.execute("""SELECT preference FROM user_preferences WHERE user_id=%s ORDER BY preference;""", (user_id,))
    # conn_psy.commit()
    user_prefs = cur.fetchall()

    prefs_wording = ''
    prefs_list = []
    if user_prefs and len(user_prefs) > 0:
        for user_pref_line in user_prefs:
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
    """return Family name from search' title"""
    # TODO: TO BE DELETED and FAM NAME to be TAKEN from SEARCHES Table and field NAME
    # TODO: add family_name from Searches table directly

    string_by_word = title_string.split()

    # exception case: when Family Name is third word
    # it happens when first two either Найден Жив or Найден Погиб with different word forms
    if string_by_word[0][0:4].lower() == "найд":
        fam_name = string_by_word[2]

    # case when "Поиск приостановлен"
    elif string_by_word[1][0:8].lower() == 'приостан':
        fam_name = string_by_word[2]

    # case when "Поиск остановлен"
    elif string_by_word[1][0:8].lower() == 'остановл':
        fam_name = string_by_word[2]

    # case when "Поиск завершен"
    elif string_by_word[1][0:6].lower() == 'заверш':
        fam_name = string_by_word[2]

    # all the other cases
    else:
        fam_name = string_by_word[1]

    return fam_name


def compose_msg_on_all_last_searches(conn_psy, cur, region):
    """Compose a part of message on the list of recent searches in the given region with relation to user's coords"""

    msg = ''

    # download the list from SEARCHES sql table
    cur.execute(
        """select s2.* from (SELECT search_forum_num, parsed_time, status_short, forum_search_title, cut_link,
        search_start_time, num_of_replies, family_name, age, id, forum_folder_id FROM searches WHERE
        forum_folder_id=%s ORDER BY search_start_time DESC LIMIT 20) s2 LEFT JOIN
        search_health_check shc ON s2.search_forum_num=shc.search_forum_num
        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular')
        ORDER BY s2.search_start_time DESC;""", (region,)
    )

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


def compose_msg_on_active_searches_in_one_reg(conn_psy, cur, region, user_data):
    """Compose a part of message on the list of active searches in the given region with relation to user's coords"""

    msg = ''

    # download the list from SEARCHES sql table
    cur.execute(
        """select s2.* from (SELECT s.search_forum_num, s.parsed_time, s.status_short, s.forum_search_title, s.cut_link,
        s.search_start_time, s.num_of_replies, s.family_name, s.age, s.id, sa.id, sa.search_id,
        sa.activity_type, sa.latitude, sa.longitude, sa.upd_time, sa.coord_type, s.forum_folder_id FROM
        searches s LEFT JOIN search_coordinates sa ON s.search_forum_num = sa.search_id WHERE
        s.status_short='Ищем' AND s.forum_folder_id=%s ORDER BY s.search_start_time DESC) s2 LEFT JOIN
        search_health_check shc ON s2.search_forum_num=shc.search_forum_num
        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') ORDER BY s2.search_start_time DESC;""",
        (region,)
    )
    # conn_psy.commit()
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


def compose_full_message_on_list_of_searches(conn_psy, cur, list_type, user_id, region, region_name):
    """Compose a Final message on the list of searches in the given region"""

    msg = ''

    cur.execute(
        "SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;", (user_id,)
    )
    # conn_psy.commit()
    user_data = cur.fetchone()

    # combine the list of last 20 searches
    if list_type == 'all':

        msg += compose_msg_on_all_last_searches(conn_psy, cur, region)

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

        msg += compose_msg_on_active_searches_in_one_reg(conn_psy, cur, region, user_data)

        if msg:
            msg = 'Актуальные поиски за 60 дней в разделе <a href="https://lizaalert.org/forum/viewforum.php?f=' \
                  + str(region) + '">' + region_name + '</a>:\n' + msg

        else:
            msg = 'В разделе <a href="https://lizaalert.org/forum/viewforum.php?f=' \
                  + str(region) + '">' + region_name + '</a> все поиски за последние 60 дней завершены.'

    return msg


def save_new_user(conn_psy, cur, user_id, input_username):
    """save the new user in the user-related tables: users, user_preferences"""

    # add the New User into table users
    cur.execute("""INSERT INTO users (user_id, username_telegram, reg_date) values (%s, %s, %s);""",
                (user_id, input_username, datetime.datetime.now()))
    # conn_psy.commit()

    # add the New User into table user_preferences
    # default setting is set as notifications on new searches & status changes
    cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                (user_id, 'new_searches', 0))
    # conn_psy.commit()
    cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                (user_id, 'status_changes', 1))
    # conn_psy.commit()
    cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                (user_id, 'bot_news', 20))
    # conn_psy.commit()

    message_for_admin = 'New user, name: ' + str(input_username) + ' id: ' + str(user_id)
    logging.info(message_for_admin)

    return None


def check_if_new_user(conn_psy, cur, user_id):
    """check if the user is new or not"""

    cur.execute("""SELECT user_id FROM users WHERE user_id=%s LIMIT 1;""", (user_id,))
    # conn_psy.commit()
    info_on_user_from_users = str(cur.fetchone())

    if info_on_user_from_users == 'None':
        user_is_new = True
    else:
        user_is_new = False

    return user_is_new


def check_if_user_has_no_regions(conn_psy, cur, user_id):
    """check if the user has at least one region"""

    cur.execute("""SELECT user_id FROM user_regional_preferences WHERE user_id=%s LIMIT 1;""", (user_id,))
    # conn_psy.commit()
    info_on_user_from_users = str(cur.fetchone())

    if info_on_user_from_users == 'None':
        no_regions = True
    else:
        no_regions = False

    return no_regions


def save_user_coordinates(conn_psy, cur, user_id, input_latitude, input_longitude):
    """Save / update user "home" coordinates"""

    cur.execute(
        "DELETE FROM user_coordinates WHERE user_id=%s;", (user_id,)
    )
    # conn_psy.commit()

    now = datetime.datetime.now()
    cur.execute("""INSERT INTO user_coordinates (user_id, latitude, longitude, upd_time) values (%s, %s, %s, %s);""",
                (user_id, input_latitude, input_longitude, now))
    # conn_psy.commit()

    return None


def show_user_coordinates(conn_psy, cur, user_id):
    """Return the saved user "home" coordinates"""

    cur.execute("""SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;""",
                (user_id,))
    # conn_psy.commit()

    try:
        lat, lon = list(cur.fetchone())
    except:  # noqa
        lat = None
        lon = None

    return lat, lon


def delete_user_coordinates(conn_psy, cur, user_id):
    """Delete the saved user "home" coordinates"""

    cur.execute(
        "DELETE FROM user_coordinates WHERE user_id=%s;", (user_id,)
    )
    # conn_psy.commit()

    return None


def distance_to_search(search_lat, search_lon, user_let, user_lon):
    """Return the distance and direction from user "home" coordinates to the search' coordinates"""

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


def get_user_regional_preferences(conn_psy, cur, user_id):
    """Return user's regional preferences"""

    user_prefs_list = []

    try:
        cur.execute("SELECT forum_folder_num FROM user_regional_preferences WHERE user_id=%s;", (user_id,))
        user_reg_prefs_array = cur.fetchall()

        # TODO: to make on SQL level not in py code
        # List of folders not to be shown
        no_show = [233, 300, 305, 310]

        for line in user_reg_prefs_array:
            if line[0] not in no_show:
                user_prefs_list.append(line[0])

        logging.info(str(user_prefs_list))

    except Exception as e:
        logging.info(f'failed to get user regional prefs for user {user_id}')
        logging.exception(e)

    return user_prefs_list


def save_preference(conn_psy, cur, user_id, preference):
    """Save user preference on types of notifications to be sent by bot"""

    # the mater-table is notif_mailing_types:
    # type_id | type_name
    # 0 | topic_new
    # 1 | topic_status_change
    # 2 | topic_title_change
    # 3 | topic_comment_new
    # 4 | topic_inforg_comment_new
    # 5 | topic_field_trip_new
    # 6 | topic_field_trip_change
    # 7 | topic_coords_change
    # 20 | bot_news
    # 30 | all
    # 99 | not_defined

    # TODO: make a SQL script to get pref_id instead of preference (name)
    # TODO: to send pref_id to each update

    # if user wants to have +ALL notifications
    if preference == 'all':
        cur.execute("""DELETE FROM user_preferences WHERE user_id=%s;""", (user_id,))
        # conn_psy.commit()

        cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                    (user_id, preference, 30))
        # conn_psy.commit()

    # if user DOESN'T want to have -ALL notifications
    elif preference == '-all':
        cur.execute("""DELETE FROM user_preferences WHERE user_id=%s;""", (user_id,))
        # conn_psy.commit()

        cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                    (user_id, 'bot_news', 20))
        # conn_psy.commit()

    # if user wants notifications on NEW SEARCHES or STATUS or TITLE updates
    elif preference in {'new_searches', 'status_changes', 'title_changes'}:

        # Check if there's "ALL" preference
        cur.execute("SELECT id FROM user_preferences WHERE user_id=%s AND preference='all' LIMIT 1;", (user_id,))
        # conn_psy.commit()
        user_had_all = str(cur.fetchone())

        #
        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR preference='finish' OR
            preference='all' OR preference=%s);""",
            (user_id, preference))
        # conn_psy.commit()

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
                    (user_id, preference, pref_id))
        # conn_psy.commit()

        # Inforg updates handling
        if user_had_all != 'None':
            cur.execute("""INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);""",
                        (user_id, 'bot_news', 20))
            # conn_psy.commit()

    # if user DOESN'T want notifications on SPECIFIC updates
    elif preference in {'-new_searches', '-status_changes'}:  # or preference == '-title_changes'
        preference = preference[1:]
        if preference == 'new_searches':
            pref_id = 0
        elif preference == 'status_changes':
            pref_id = 1
        else:
            pref_id = 99
        cur.execute("""DELETE FROM user_preferences WHERE user_id = %s AND pref_id = %s;""",
                    (user_id, pref_id))
        # conn_psy.commit()

        cur.execute("SELECT id FROM user_preferences WHERE user_id=%s LIMIT 1;", (user_id,))
        # conn_psy.commit()

    # if user wants notifications ON COMMENTS
    elif preference == 'comments_changes':

        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR
            preference='all' OR preference='finish' OR preference='inforg_comments');""",
            (user_id,))
        # conn_psy.commit()

        cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                    (user_id, preference, 3))
        # conn_psy.commit()

    # if user DOESN'T want notifications on COMMENTS
    elif preference == '-comments_changes':

        cur.execute("""DELETE FROM user_preferences WHERE user_id = %s AND preference = 'comments_changes';""",
                    (user_id,))
        # conn_psy.commit()

        cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                    (user_id, 'inforg_comments', 4))
        # conn_psy.commit()

    # if user wants notifications ON INFORG COMMENTS
    elif preference == 'inforg_comments':

        # Delete Start & Finish
        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR
            preference='finish' OR preference='inforg_comments');""",
            (user_id,))
        # conn_psy.commit()

        # Check if ALL of Comments_changes are in place
        cur.execute(
            """SELECT id FROM user_preferences WHERE user_id=%s AND (preference='all' OR
            preference='comments_changes' OR pref_id=30 OR pref_id=3) LIMIT 1;""",
            (user_id,))
        # conn_psy.commit()
        info_on_user = str(cur.fetchone())

        # Add Inforg_comments ONLY in there's no ALL or Comments_changes
        if info_on_user == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                        (user_id, preference, 4))
            # conn_psy.commit()

    # if user DOESN'T want notifications ON INFORG COMMENTS
    elif preference == '-inforg_comments':

        cur.execute("""DELETE FROM user_preferences WHERE user_id = %s AND (preference = 'inforg_comments');""",
                    (user_id,))
        # conn_psy.commit()

    # if user wants notifications ON BOT NEWS
    elif preference == 'bot_news':

        # Delete Start & Finish
        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR
            preference='finish' OR preference='bot_news');""",
            (user_id,))
        # conn_psy.commit()

        # Check if ALL is in place
        cur.execute(
            "SELECT id FROM user_preferences WHERE user_id=%s AND (preference='all' OR pref_id=30) LIMIT 1;",
            (user_id,))
        # conn_psy.commit()
        already_all = str(cur.fetchone())

        # Add Bot_News ONLY in there's no ALL
        if already_all == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                        (user_id, preference, 20))
            # conn_psy.commit()

    # if user DOESN'T want notifications ON BOT NEWS
    elif preference == '-bot_news':

        cur.execute(
            """DELETE FROM user_preferences WHERE user_id = %s AND (preference = 'bot_news' OR pref_id=20);""",
            (user_id,))
        # conn_psy.commit()

    # if user wants notifications ON NEW FIELD TRIPS
    elif preference == 'field_trips_new':

        # Delete Start & Finish
        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR
            preference='finish' OR preference='field_trips_new' OR pref_id=5);""",
            (user_id,))
        # conn_psy.commit()

        # Check if ALL is in plac
        cur.execute(
            "SELECT id FROM user_preferences WHERE user_id=%s AND (preference='all' or pref_id=30) LIMIT 1;",
            (user_id,))
        # conn_psy.commit()
        already_all = str(cur.fetchone())

        # Add new_filed_trips ONLY in there's no ALL
        if already_all == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                        (user_id, preference, 5))
            # conn_psy.commit()

    # if user DOESN'T want notifications ON FIELD TRIPS
    elif preference == '-field_trips_new':

        cur.execute(
            """DELETE FROM user_preferences WHERE user_id = %s AND (preference = 'field_trips_new' OR pref_id=5);""",
            (user_id,))
        # conn_psy.commit()

    # if user wants notifications ON NEW FIELD TRIPS
    elif preference == 'field_trips_change':

        # Delete Start & Finish
        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR
            preference='finish' OR preference='field_trips_change' OR pref_id=6);""",
            (user_id,))
        # conn_psy.commit()

        # Check if ALL is in place
        cur.execute(
            "SELECT id FROM user_preferences WHERE user_id=%s AND (preference='all' or pref_id=30) LIMIT 1;",
            (user_id,))
        # conn_psy.commit()
        already_all = str(cur.fetchone())

        # Add filed_trips_change ONLY in there's no ALL
        if already_all == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                        (user_id, preference, 6))
            # conn_psy.commit()

    # if user DOESN'T want notifications ON FIELD TRIPS CHANGES
    elif preference == '-field_trips_change':

        cur.execute(
            """DELETE FROM user_preferences WHERE user_id = %s AND (preference = 'field_trips_change' OR pref_id=6);""",
            (user_id,))
        # conn_psy.commit()

    # if user wants notifications ON COORDS CHANGE
    elif preference == 'coords_change':

        # Delete Start & Finish
        cur.execute(
            """DELETE FROM user_preferences WHERE user_id=%s AND (preference='start' OR
            preference='finish' OR preference='coords_change' OR pref_id=7);""",
            (user_id,))
        # conn_psy.commit()

        # Check if ALL is in place
        cur.execute(
            "SELECT id FROM user_preferences WHERE user_id=%s AND (preference='all' OR pref_id=30) LIMIT 1;",
            (user_id,))
        # conn_psy.commit()
        already_all = str(cur.fetchone())

        # Add new_filed_trips ONLY in there's no ALL
        if already_all == 'None':
            cur.execute("INSERT INTO user_preferences (user_id, preference, pref_id) values (%s, %s, %s);",
                        (user_id, preference, 7))
            # conn_psy.commit()

    # if user DOESN'T want notifications ON COORDS CHANGE
    elif preference == '-coords_change':

        cur.execute(
            """DELETE FROM user_preferences WHERE user_id = %s AND (preference = 'coords_change' OR pref_id=7);""",
            (user_id,))
        # conn_psy.commit()

    return None


def update_and_download_list_of_regions(conn_psy, cur, user_id, got_message, b_menu_set_region, b_fed_dist_pick_other):
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
    rev_reg_dict = {value[0]: key for (key, value) in reg_dict.items()}

    # case for the first entry to the screen of Reg Settings
    if got_message == b_menu_set_region:
        is_first_entry = 'yes'
    elif got_message in fed_okr_dict or got_message == b_fed_dist_pick_other:
        pass
    else:
        try:

            list_of_regs_to_upload = reg_dict[got_message]

            # any region
            cur.execute(
                """SELECT forum_folder_num from user_regional_preferences WHERE user_id=%s;""", (user_id,)
            )
            # conn_psy.commit()
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
                    # conn_psy.commit()

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
                    # conn_psy.commit()

        except Exception as e:
            logging.info('failed to upload & download the list of user\'s regions')
            logging.exception(e)

    # Get the list of resulting regions
    cur.execute(
        """SELECT forum_folder_num from user_regional_preferences WHERE user_id=%s;""", (user_id,)
    )
    # conn_psy.commit()
    user_curr_regs = cur.fetchall()
    user_curr_regs_list = [reg[0] for reg in user_curr_regs]

    for reg in user_curr_regs_list:
        if reg in rev_reg_dict:
            msg += ',\n &#8226; ' + rev_reg_dict[reg]

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


def get_last_bot_msg(conn_psy, cur, user_id):
    """Get the last bot message to user to define if user is expected to give exact answer"""

    cur.execute(
        """
        SELECT msg_type FROM msg_from_bot WHERE user_id=%s LIMIT 1;
        """, (user_id,))
    # conn_psy.commit()
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


def main(request):
    """Main function to orchestrate the whole script"""

    # Set basic params
    bot_token = get_secrets("bot_api_token__prod")

    bot = Bot(token=bot_token)

    with sql_connect_by_psycopg2() as conn_psy, conn_psy.cursor() as cur:

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

            username = get_param_if_exists(update, 'update.effective_message.from_user.username')

            # the purpose of this bot - sending messages to unique users, this way
            # chat_id is treated as user_id and vice versa (which is not true in general)

            # TODO: below are user_id - but it all the same. to be merged
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
                logging.error('failed to define user_id')

            # CASE 1 – when user blocked / unblocked the bot
            if user_new_status in {'kicked', 'member'}:
                try:
                    status_dict = {'kicked': 'block_user', 'member': 'unblock_user'}

                    # mark user as blocked in psql
                    message_for_pubsub = {'action': status_dict[user_new_status], 'info': {'user': user_id}}
                    publish_to_pubsub('topic_for_user_management', message_for_pubsub)

                    # TODO: in case of unblock – send a message "welcome back, please let us know how to improve?"

                except Exception as e:
                    logging.info('Error in finding basic data for block/unblock user in Communicate script')
                    logging.exception(e)

            # CASE 2 – when user changed auto-delete setting in the bot
            elif timer_changed:
                logging.info('user changed auto-delete timer settings')

            # CASE 3 – when user sends a PHOTO
            elif photo:
                logging.debug('user sends photos to bot')
                # TODO: it should be avoided for now - but in future we can be able to receive QR codes
                bot.sendMessage(chat_id=user_id, text='Спасибо, интересное! Только бот не работает с изображениями '
                                                      'и отвечает только на определенные текстовые команды.')

            # CASE 4 – when some Channel writes to bot
            elif channel_type and user_id < 0:
                notify_admin('[comm]: INFO: CHANNEL sends messages to bot!')

                try:
                    bot.leaveChat(user_id)
                    notify_admin('[comm]: INFO: we have left the CHANNEL!')

                except Exception as e:
                    logging.error('[comm]: Leaving channel was not successful:' + repr(e))

            # CASE 5 – when user sends Contact
            elif contact:
                bot.sendMessage(chat_id=user_id, text='Спасибо, буду знать. Вот только бот не работает с контактами '
                                                      'и отвечает только на определенные текстовые команды.')

            # CASE 6 – when user mentions bot as @LizaAlert_Searcher_Bot in another telegram chat. Bot should do nothing
            elif inline_query:
                notify_admin('[comm]: User mentioned bot in some chats')

            # CASE 7 – regular messaging with bot
            else:

                # check if user is new - and if so - saving him/her
                user_is_new = check_if_new_user(conn_psy, cur, user_id)
                if user_is_new:
                    # TODO: to replace with another user_management script?
                    save_new_user(conn_psy, cur, user_id, username)

                # get user regional settings (which regions he/she is interested it)
                user_regions = get_user_regional_preferences(conn_psy, cur, user_id)

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
                b_act_field_trips_new = 'включить: о новых выездах'
                b_act_field_trips_change = 'включить: об изменениях в выездах'
                b_act_coords_change = 'включить: о смене места штаба'
                com_9 = 'включить: о новых функциях бота'
                com_15 = 'отключить и настроить более гибко'
                com_16 = 'отключить: о новых поисках'
                com_17 = 'отключить: об изменениях статусов'
                com_18 = 'отключить: о всех новых комментариях'
                b_deact_inforg_com = 'отключить: о комментариях Инфорга'
                b_deact_field_trips_new = 'отключить: о новых выездах'
                b_deact_field_trips_change = 'отключить: об изменениях в выездах'
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
                bot_request_bfr_usr_msg = get_last_bot_msg(conn_psy, cur, user_id)

                if bot_request_bfr_usr_msg:
                    logging.info(f'before this message bot was waiting for {bot_request_bfr_usr_msg} '
                                 f'from user {user_id}')
                else:
                    logging.info(f'before this message bot was NOT waiting anything from user {user_id}')

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

                            save_user_coordinates(conn_psy, cur, user_id, user_latitude, user_longitude)
                            bot_message = 'Ваши "домашние координаты" сохранены:\n'
                            bot_message += generate_yandex_maps_place_link(user_latitude, user_longitude, 'coords')
                            bot_message += '\nТеперь для всех поисков, где удастся распознать координаты штаба или ' \
                                           'населенного пункта, будет указываться направление и расстояние по ' \
                                           'прямой от ваших "домашних координат".'

                            keyboard_settings = [[b_coords_auto_def], [b_coords_man_def], [b_coords_check],
                                                 [b_coords_del], [b_back_to_start]]
                            reply_markup = ReplyKeyboardMarkup(keyboard_settings, resize_keyboard=True)

                            bot.sendMessage(chat_id=user_id, text=bot_message, reply_markup=reply_markup,
                                            parse_mode='HTML', disable_web_page_preview=True)
                            msg_sent_by_specific_code = True

                            # saving the last message from bot
                            if not bot_request_aft_usr_msg:
                                bot_request_aft_usr_msg = 'not_defined'

                            try:
                                cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))
                                # conn_psy.commit()

                                cur.execute(
                                    """
                                    INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);
                                    """,
                                    (user_id, datetime.datetime.now(), bot_request_aft_usr_msg))
                                # conn_psy.commit()

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
                            # conn_psy.commit()
                            regions_table = cur.fetchall()

                            region_name = ''
                            for region in user_regions:
                                for line in regions_table:

                                    if line[0] == region:
                                        region_name = line[1]
                                        break

                                # check if region – is an archive folder: if so – it can be sent only to 'all'
                                if region_name.find('аверш') == -1 or temp_dict[got_message] == 'all':

                                    bot_message = compose_full_message_on_list_of_searches(conn_psy, cur,
                                                                                           temp_dict[got_message],
                                                                                           user_id,
                                                                                           region, region_name)
                                    reply_markup = reply_markup_main

                                    bot.sendMessage(chat_id=user_id, text=bot_message, reply_markup=reply_markup,
                                                    parse_mode='HTML', disable_web_page_preview=True)

                                    # saving the last message from bot
                                    try:
                                        cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))
                                        # conn_psy.commit()

                                        cur.execute(
                                            """
                                            INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);
                                            """,
                                            (user_id, datetime.datetime.now(), 'report'))
                                        # conn_psy.commit()

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
                                          'на 100% корректно. Если заметите случаи некорректного выполнения ' \
                                          'функционала из этого раздела – пишите, пожалуйста, в телеграм-чат ' \
                                          'https://t.me/joinchat/2J-kV0GaCgwxY2Ni'
                            keyboard_coordinates_admin = [[b_act_field_trips_new], [b_deact_field_trips_new],
                                                          [b_act_field_trips_change], [b_deact_field_trips_change],
                                                          [b_act_coords_change], [b_deact_coords_change],
                                                          [b_back_to_start]]
                            reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

                        # If user Region is Moscow or not
                        elif got_message == b_reg_moscow:
                            bot_message = 'Спасибо, бот запомнил этот выбор и теперь вы сможете получать ключевые ' \
                                          'уведомления в регионе Москва и МО. Вы в любой момент сможете изменить ' \
                                          'список регионов через настройки бота.'
                            reply_markup = reply_markup_main

                            if check_if_user_has_no_regions:
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

                        elif got_message == b_reg_not_moscow:
                            bot_message = 'Спасибо, тогда, пожалуйста, выберите хотя бы один регион поисков, ' \
                                          'чтобы начать получать уведомления. Вы в любой момент сможете изменить ' \
                                          'список регионов через настройки бота.'
                            keyboard = [[b_menu_set_region], [b_back_to_start]]
                            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                        # TODO: for debugging purposes only
                        elif got_message.lower() == 'go':
                            publish_to_pubsub('topic_notify_admin', 'test_admin_check')

                        elif got_message == b_other:
                            bot_message = 'Здесь можно посмотреть статистику по 20 последним поискам, перейти в ' \
                                          'канал Коммъюнити или Прочитать важную информацию для Новичка'
                            reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

                        elif got_message in {b_menu_set_region, b_fed_dist_pick_other}:
                            bot_message = update_and_download_list_of_regions(conn_psy, cur,
                                                                              user_id, got_message,
                                                                              b_menu_set_region,
                                                                              b_fed_dist_pick_other)
                            reply_markup = ReplyKeyboardMarkup(keyboard_fed_dist_set, resize_keyboard=True)

                        elif got_message in dict_of_fed_dist:
                            updated_regions = update_and_download_list_of_regions(conn_psy, cur,
                                                                                  user_id, got_message,
                                                                                  b_menu_set_region,
                                                                                  b_fed_dist_pick_other)
                            bot_message = updated_regions
                            reply_markup = ReplyKeyboardMarkup(dict_of_fed_dist[got_message], resize_keyboard=True)

                        elif got_message in full_dict_of_regions:
                            updated_regions = update_and_download_list_of_regions(conn_psy, cur,
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

                        elif got_message == com_27:
                            bot_message = 'Это раздел с настройками. Здесь вы можете выбрать удобные для вас ' \
                                          'уведомления, а также ввести свои "домашние координаты", на основе которых ' \
                                          'будет рассчитываться расстояние и направление до места поиска. Вы в любой ' \
                                          'момент сможете изменить эти настройки.'
                            keyboard_settings = [[b_menu_set_region], [b_settings_coords], [com_3], [b_back_to_start]]
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
                            delete_user_coordinates(conn_psy, cur, user_id)
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

                            lat, lon = show_user_coordinates(conn_psy, cur, user_id)
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

                        elif got_message == b_back_to_start:
                            bot_message = 'возвращаемся в главное меню'
                            reply_markup = reply_markup_main

                        # save preference for -ALL
                        elif got_message == com_15:
                            bot_message = 'Уведомления отключены. Кстати, их можно настроить более гибко'
                            save_preference(conn_psy, cur, user_id, '-all')
                            keyboard_notifications_all_quit = [[com_4], [com_5], [com_6], [com_7], [com_12],
                                                               [b_back_to_start]]
                            reply_markup = ReplyKeyboardMarkup(keyboard_notifications_all_quit, resize_keyboard=True)

                        # save preference for +ALL
                        elif got_message == com_4:
                            bot_message = 'Супер! теперь вы будете получать уведомления в телеграм в случаях: ' \
                                          'появление нового поиска, изменение статуса поиска (стоп, НЖ, НП), ' \
                                          'появление новых комментариев по всем поискам. Вы в любой момент можете ' \
                                          'изменить список уведомлений'
                            save_preference(conn_psy, cur, user_id, 'all')
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
                                          'официальное обучение, а вы уже готовы выехать на поиск – этот ресурс ' \
                                          'для вас.'
                            keyboard_other = [[com_1], [b_goto_community], [b_goto_first_search], [b_back_to_start]]
                            reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

                        # special block for flexible menu on notification preferences
                        elif got_message in {com_5, com_6, com_10, com_7, com_3, com_17, com_18, com_16, com_9, com_12,
                                             b_act_inforg_com, b_deact_inforg_com,
                                             b_act_field_trips_new, b_deact_field_trips_new,
                                             b_act_field_trips_change, b_deact_field_trips_change,
                                             b_act_coords_change, b_deact_coords_change}:

                            # save preference for +NEW SEARCHES
                            if got_message == com_5:
                                bot_message = 'Отлично! Теперь вы будете получать уведомления в телеграм при ' \
                                              'появлении нового поиска. Вы в любой момент можете изменить ' \
                                              'список уведомлений'
                                save_preference(conn_psy, cur, user_id, 'new_searches')

                            # save preference for -NEW SEARCHES
                            elif got_message == com_16:
                                bot_message = 'Записали'
                                save_preference(conn_psy, cur, user_id, '-new_searches')

                            # save preference for +BotNews
                            elif got_message == com_9:
                                bot_message = 'Теперь в случае появления нового функционала бота вы узнаете об ' \
                                              'этом в небольшом новостном сообщении'
                                save_preference(conn_psy, cur, user_id, 'bot_news')

                            # save preference for -BotNews
                            elif got_message == com_12:
                                bot_message = 'Вы отписались от уведомлений по новому функционалу бота. Когда ' \
                                              'появится какая-либо новая функция - бот, к сожалению, не сможет вам ' \
                                              'об этом сообщить.'
                                save_preference(conn_psy, cur, user_id, '-bot_news')

                            # save preference for +STATUS UPDATES
                            elif got_message == com_6:
                                bot_message = 'Отлично! теперь вы будете получать уведомления в телеграм при ' \
                                              'изменении статуса поисков (НЖ, НП, СТОП и т.п.). Вы в любой момент ' \
                                              'можете изменить список уведомлений'
                                save_preference(conn_psy, cur, user_id, 'status_changes')

                            # save preference for -STATUS UPDATES
                            elif got_message == com_17:
                                bot_message = 'Записали'
                                save_preference(conn_psy, cur, user_id, '-status_changes')

                            # save preference for TITLE UPDATES
                            elif got_message == com_10:
                                bot_message = 'Отлично!'
                                save_preference(conn_psy, cur, user_id, 'title_changes')

                            # save preference for +COMMENTS
                            elif got_message == com_7:
                                bot_message = 'Отлично! Теперь все новые комментарии будут у вас! Вы в любой момент ' \
                                              'можете изменить список уведомлений'
                                save_preference(conn_psy, cur, user_id, 'comments_changes')

                            # save preference for -COMMENTS
                            elif got_message == com_18:
                                bot_message = 'Записали. Мы только оставили вам включенными уведомления о ' \
                                              'комментариях Инфорга. Их тоже можно отключить'
                                save_preference(conn_psy, cur, user_id, '-comments_changes')

                            # save preference for +InforgComments
                            elif got_message == b_act_inforg_com:
                                bot_message = 'Если вы не подписаны на уведомления по всем комментариям, то теперь ' \
                                              'вы будете получать уведомления о комментариях от Инфорга. Если же вы ' \
                                              'уже подписаны на все комментарии – то всё остаётся без изменений: бот ' \
                                              'уведомит вас по всем комментариям, включая от Инфорга'
                                save_preference(conn_psy, cur, user_id, 'inforg_comments')

                            # save preference for -InforgComments
                            elif got_message == b_deact_inforg_com:
                                bot_message = 'Вы отписались от уведомлений по новым комментариям от Инфорга'
                                save_preference(conn_psy, cur, user_id, '-inforg_comments')

                            # save preference for +FieldTripsNew
                            elif got_message == b_act_field_trips_new:
                                bot_message = 'Теперь вы будете получать уведомления о новых выездах по уже идущим ' \
                                              'поискам. Обратите внимание, что это не рассылка по новым темам на ' \
                                              'форуме, а именно о том, что в существующей теме в ПЕРВОМ посте ' \
                                              'появилась информация о новом выезде'
                                save_preference(conn_psy, cur, user_id, 'field_trips_new')

                            # save preference for -FieldTripsNew
                            elif got_message == b_deact_field_trips_new:
                                bot_message = 'Вы отписались от уведомлений по новым выездам'
                                save_preference(conn_psy, cur, user_id, '-field_trips_new')

                            # save preference for +FieldTripsChange
                            elif got_message == b_act_field_trips_change:
                                bot_message = 'Теперь вы будете получать уведомления о ключевых изменениях при ' \
                                              'выездах, в т.ч. изменение или завершение выезда. Обратите внимание, ' \
                                              'что эта рассылка отражает изменения только в ПЕРВОМ посте поиска.'
                                save_preference(conn_psy, cur, user_id, 'field_trips_change')

                            # save preference for -FieldTripsChange
                            elif got_message == b_deact_field_trips_change:
                                bot_message = 'Вы отписались от уведомлений по изменениям выездов'
                                save_preference(conn_psy, cur, user_id, '-field_trips_change')

                            # save preference for +CoordsChange
                            elif got_message == b_act_coords_change:
                                bot_message = 'Если у штаба поменяются координаты (и об этом будет написано в первом ' \
                                              'посте на форуме) – бот уведомит вас об этом'
                                save_preference(conn_psy, cur, user_id, 'coords_change')

                            # save preference for -CoordsChange
                            elif got_message == b_deact_coords_change:
                                bot_message = 'Вы отписались от уведомлений о смене места (координат) штаба'
                                save_preference(conn_psy, cur, user_id, '-coords_change')

                            # GET what are preferences
                            elif got_message == com_3:
                                prefs = compose_user_preferences_message(conn_psy, cur, user_id)
                                if prefs[0] == 'пока нет включенных уведомлений' or prefs[0] == 'неизвестная настройка':
                                    bot_message = 'Выберите, какие уведомления вы бы хотели получать'
                                else:
                                    bot_message = 'Сейчас у вас включены следующие виды уведомлений:\n'
                                    bot_message += prefs[0]

                            else:
                                bot_message = 'empty message'

                            # getting the list of user notification preferences
                            prefs = compose_user_preferences_message(conn_psy, cur, user_id)
                            keyboard_notifications_flexible = [[com_4], [com_5], [com_6], [com_7], [b_act_inforg_com],
                                                               [com_9], [b_back_to_start]]
                            # just a comparison with negative [[com_15],[com_16],[com_17],[com_18],[b_deact_inforg_com],
                            #                                  [com_12],[b_back_to_start]]

                            for line in prefs[1]:
                                if line == 'all':
                                    keyboard_notifications_flexible = [[com_15], [b_back_to_start]]
                                elif line == 'new_searches':
                                    keyboard_notifications_flexible[1] = [com_16]
                                elif line == 'status_changes':
                                    keyboard_notifications_flexible[2] = [com_17]
                                elif line == 'comments_changes':
                                    keyboard_notifications_flexible[3] = [com_18]
                                elif line == 'inforg_comments':
                                    keyboard_notifications_flexible[4] = [b_deact_inforg_com]
                                elif line == 'bot_news':
                                    keyboard_notifications_flexible[5] = [com_12]
                                # TODO: to be added coords_change and field_trip_changes

                            reply_markup = ReplyKeyboardMarkup(keyboard_notifications_flexible, resize_keyboard=True)

                        # in case of other user messages:
                        else:
                            # If command in unknown
                            bot_message = 'не понимаю такой команды, пожалуйста, используйте кнопки со стандартными ' \
                                          'командами ниже'
                            bot_message += reply_to_message_text
                            reply_markup = reply_markup_main

                        if not msg_sent_by_specific_code:
                            bot.sendMessage(chat_id=user_id, text=bot_message, reply_markup=reply_markup,
                                            parse_mode='HTML', disable_web_page_preview=True)

                        # saving the last message from bot
                        if not bot_request_aft_usr_msg:
                            bot_request_aft_usr_msg = 'not_defined'

                        try:
                            cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))
                            # conn_psy.commit()

                            cur.execute(
                                """
                                INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);
                                """,
                                (user_id, datetime.datetime.now(), bot_request_aft_usr_msg))
                            # conn_psy.commit()
                        except Exception as e:
                            logging.info(f'failed updates of table msg_from_bot for user={user_id}')
                            logging.exception(e)

                    else:
                        logging.info('DBG.C.6. THERE IS a COMM SCRIPT INVOCATION w/O MESSAGE OR COORDINATES:')
                        logging.info(str(update))
                        text_for_admin = f'[comm]: Empty message in Comm, user={user_id}, username={username}, ' \
                                         f'got_message={got_message}, update={update}, ' \
                                         f'bot_request_bfr_usr_msg={bot_request_bfr_usr_msg}'
                        notify_admin(text_for_admin)

                except Exception as e:
                    logging.info('GENERAL COMM CRASH:')
                    logging.exception(e)
                    notify_admin('[comm] general script fail')

    conn_psy.close()

    return None
