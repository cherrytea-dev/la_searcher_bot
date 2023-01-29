"""compose and save all the text / location messages, then initiate sending via pub-sub"""

import os
import base64

import ast
import re
import datetime
import json
import logging
import math

import sqlalchemy

from google.cloud import secretmanager
from google.cloud import pubsub_v1


project_id = os.environ["GCP_PROJECT"]
client = secretmanager.SecretManagerServiceClient()
publisher = pubsub_v1.PublisherClient()
new_records_list = []
users_list = []
coordinates_format = "{0:.5f}"
stat_list_of_recipients = []  # list of users who received notification on new search
fib_list = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]


def sql_connect():
    """connect to google cloud sql"""

    db_user = get_secrets("cloud-postgres-username")
    db_pass = get_secrets("cloud-postgres-password")
    db_name = get_secrets("cloud-postgres-db-name")
    db_conn = get_secrets("cloud-postgres-connection-name")
    db_config = {
        "pool_size": 5,
        "max_overflow": 0,
        "pool_timeout": 0,  # seconds
        "pool_recycle": 60,  # seconds
    }

    try:
        pool = sqlalchemy.create_engine(
            sqlalchemy.engine.url.URL(
                'postgresql+pg8000',
                username=db_user,
                password=db_pass,
                database=db_name,
                query={'unix_sock': f'/cloudsql/{db_conn}/.s.PGSQL.5432'}),
            **db_config
        )
        pool.dialect.description_encoding = None
        logging.info('sql connection set')

    except Exception as e:
        logging.error('sql connection was not set: ' + repr(e))
        logging.exception(e)
        pool = None

    return pool


def get_secrets(secret_request):
    """get secret stored in GCP"""

    name = f"projects/{project_id}/secrets/{secret_request}/versions/latest"
    response = client.access_secret_version(name=name)

    return response.payload.data.decode("UTF-8")


def age_writer(age):
    """compose an age string with the right form of years in Russian"""

    if age:
        a = age // 100
        b = (age - a * 100) // 10
        c = age - a * 100 - b * 10
        if c == 1 and b != 1:
            wording = str(age) + " год"
        elif (c == 2 or c == 3 or c == 4) and b != 1:
            wording = str(age) + " года"
        else:
            wording = str(age) + " лет"
    else:
        wording = ''

    return wording


def define_family_name(title_string, predefined_fam_name):
    """define family name if it's not available as A SEPARATE FIELD in Searches table"""

    # if family name is already defined
    if predefined_fam_name:
        fam_name = predefined_fam_name

    # if family name needs to be defined
    else:
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

        # all the other cases
        else:
            fam_name = string_by_word[1]

    return fam_name


def define_dist_and_dir_to_search(search_lat, search_lon, user_let, user_lon):
    """define direction & distance from user's home coordinates to search coordinates"""

    earth_radius = 6373.0  # radius of the Earth

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

    distance = earth_radius * c
    dist = round(distance)

    # define direction

    def calc_bearing(lat_2, lon_2, lat_1, lon_1):
        d_lon_ = (lon_2 - lon_1)
        x = math.cos(math.radians(lat_2)) * math.sin(math.radians(d_lon_))
        y = math.cos(math.radians(lat_1)) * math.sin(math.radians(lat_2)) - math.sin(math.radians(lat_1)) * math.cos(
            math.radians(lat_2)) * math.cos(math.radians(d_lon_))
        bearing = math.atan2(x, y)  # used to determine the quadrant
        bearing = math.degrees(bearing)

        return bearing

    def calc_direction(lat_1, lon_1, lat_2, lon_2):
        points = ['&#8593;&#xFE0E;', '&#x2197;&#xFE0F;', '&#8594;&#xFE0E;', '&#8600;&#xFE0E;', '&#8595;&#xFE0E;',
                  '&#8601;&#xFE0E;', '&#8592;&#xFE0E;', '&#8598;&#xFE0E;']
        bearing = calc_bearing(lat_1, lon_1, lat_2, lon_2)
        bearing += 22.5
        bearing = bearing % 360
        bearing = int(bearing / 45)  # values 0 to 7
        nsew = points[bearing]

        return nsew

    direction = calc_direction(lat1, lon1, lat2, lon2)

    return dist, direction


def process_pubsub_message(event):
    """get the readable message from incoming pub/sub call"""

    # receive message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
    else:
        received_message_from_pubsub = 'I cannot read message from pub/sub'
    encoded_to_ascii = eval(received_message_from_pubsub)
    data_in_ascii = encoded_to_ascii['data']
    message_in_ascii = str(data_in_ascii['message'])

    logging.info('LOGGING-INFO: incoming Pub/Sub message: ' + str(message_in_ascii))

    return message_in_ascii


class Comment:
    def __init__(self,
                 comment_url=None,
                 comment_text=None,
                 comment_author_nickname=None,
                 comment_author_link=None,
                 search_forum_num=None,
                 comment_num=None,
                 comment_forum_global_id=None,
                 ignore=None
                 ):
        self.comment_url = comment_url
        self.comment_text = comment_text
        self.comment_author_nickname = comment_author_nickname
        self.comment_author_link = comment_author_link
        self.search_forum_num = search_forum_num
        self.comment_num = comment_num
        self.comment_forum_global_id = comment_forum_global_id
        self.ignore = ignore

    def __str__(self):
        return str([self.comment_url, self.comment_text, self.comment_author_nickname, self.comment_author_link,
                    self.search_forum_num, self.comment_num, self.comment_forum_global_id, self.ignore])


class LineInChangeLog:
    def __init__(self,
                 forum_search_num=None,
                 change_type=None,  # it is int from 0 to 99 which represents "change_type" column in change_log
                 changed_field=None,
                 change_id=None,  # means change_log_id
                 new_value=None,
                 name=None,
                 link=None,
                 status=None,
                 n_of_replies=None,
                 title=None,
                 age=None,
                 age_wording=None,
                 forum_folder=None,
                 search_latitude=None,
                 search_longitude=None,
                 activities=None,
                 comments=None,
                 comments_inforg=None,
                 message=None,
                 processed=None,
                 managers=None,
                 start_time=None,
                 ignore=None,
                 region=None,
                 coords_change_type=None
                 ):
        self.forum_search_num = forum_search_num
        self.change_type = change_type
        self.changed_field = changed_field
        self.change_id = change_id
        self.new_value = new_value
        self.name = name
        self.link = link
        self.status = status
        self.n_of_replies = n_of_replies
        self.title = title
        self.age = age
        self.age_wording = age_wording
        self.forum_folder = forum_folder
        self.search_latitude = search_latitude
        self.search_longitude = search_longitude
        self.activities = activities
        self.comments = comments
        self.comments_inforg = comments_inforg
        self.message = message
        self.processed = processed
        self.managers = managers
        self.start_time = start_time
        self.ignore = ignore
        self.region = region
        self.coords_change_type = coords_change_type

    def __str__(self):
        return str([self.forum_search_num, self.change_type, self.changed_field, self.new_value, self.change_id,
                    self.name, self.link,
                    self.status, self.n_of_replies, self.title, self.age, self.age_wording, self.forum_folder,
                    self.search_latitude, self.search_longitude, self.activities, self.comments, self.comments_inforg,
                    self.message, self.processed, self.managers, self.start_time, self.ignore, self.region,
                    self.coords_change_type])


class User:
    def __init__(self,
                 user_id=None,
                 username_telegram=None,
                 notification_preferences=None,
                 notif_pref_ids_list=None,
                 user_latitude=None,
                 user_longitude=None,
                 user_regions=None,
                 user_in_multi_regions=True,
                 user_corr_regions=None,
                 user_new_search_notifs=None,
                 user_role=None,
                 user_age_periods=None # noqa
                 ):
        user_age_periods = []
        self.user_id = user_id
        self.username_telegram = username_telegram
        self.notification_preferences = notification_preferences
        self.notif_pref_ids_list = notif_pref_ids_list
        self.user_latitude = user_latitude
        self.user_longitude = user_longitude
        self.user_regions = user_regions
        self.user_in_multi_regions = user_in_multi_regions
        self.user_corr_regions = user_corr_regions
        self.user_new_search_notifs = user_new_search_notifs
        self.role = user_role
        self.age_periods = user_age_periods

    def __str__(self):
        return str([self.user_id, self.username_telegram, self.notification_preferences, self.notif_pref_ids_list,
                    self.user_latitude, self.user_longitude, self.user_regions, self.user_in_multi_regions,
                    self.user_corr_regions, self.user_new_search_notifs, self.age_periods])


def compose_new_records_from_change_log(conn):
    """compose the New Records list of the unique New Records in Change Log: one Record = One line in Change Log"""

    global new_records_list

    delta_in_cl = conn.execute(
        """SELECT search_forum_num, changed_field, new_value, id, change_type FROM change_log 
        WHERE notification_sent is NULL 
        OR notification_sent='s' ORDER BY id LIMIT 1; """
    ).fetchall()

    for i in range(len(delta_in_cl)):
        one_line_in_change_log = list(delta_in_cl[i])
        new_line = LineInChangeLog()
        new_line.forum_search_num = one_line_in_change_log[0]
        new_line.changed_field = one_line_in_change_log[1]
        new_line.new_value = one_line_in_change_log[2]
        new_line.change_id = one_line_in_change_log[3]
        new_line.change_type = one_line_in_change_log[4]

        try:
            # define if this Record in change log is about New comments and New comments were already loaded into msgs
            decision = 'add'

            if len(new_records_list) > 0 and new_line.change_type == 3:  # 'replies_num_change':
                for j in new_records_list:
                    if j.forum_search_num == new_line.forum_search_num and j.change_type == new_line.change_type:
                        decision = 'drop'
            if decision == 'add':
                new_records_list.append(new_line)

        except Exception as e:
            new_records_list.append(new_line)
            logging.warning('massages_array addition were done as Exception: ' + str(e))

        del new_line

    logging.info('New Records List composed from Change Log')
    logging.info('New Records List:')
    for line in new_records_list:
        logging.info(str(line))

    return None


def enrich_new_records_from_searches(conn):
    """add the additional data from Searches into New Records list"""

    global new_records_list

    try:

        # TODO: in the future there's a need to limit the number of searches in this query (limit by time?)
        # TODO: MEMO: as of Jan 2022 - there are 5000 lines – not so crucially much
        searches_extract = conn.execute(
            """SELECT ns.*, rtf.folder_description FROM 
            (SELECT s.search_forum_num, s.status_short, s.forum_search_title,  
            s.num_of_replies, s.family_name, s.age, s.forum_folder_id, 
            sa.latitude, sa.longitude, s.search_start_time FROM searches as s LEFT JOIN 
            search_coordinates as sa ON s.search_forum_num=sa.search_id) ns LEFT JOIN 
            regions_to_folders rtf ON ns.forum_folder_id = rtf.forum_folder_id 
            ORDER BY ns.search_forum_num DESC;"""
        ).fetchall()

        # look for matching Forum Search Numbers in New Records List & Searches
        for r_line in new_records_list:
            for s_line in searches_extract:
                # when match is found
                if r_line.forum_search_num == s_line[0]:
                    r_line.status = s_line[1]
                    r_line.link = 'https://lizaalert.org/forum/viewtopic.php?t=' + str(r_line.forum_search_num)
                    r_line.title = s_line[2]
                    r_line.n_of_replies = s_line[3]
                    r_line.name = define_family_name(r_line.title, s_line[4])  # cuz not all the records has names in S
                    r_line.age = s_line[5]
                    r_line.age_wording = age_writer(s_line[5])
                    r_line.forum_folder = s_line[6]
                    r_line.search_latitude = s_line[7]
                    r_line.search_longitude = s_line[8]
                    r_line.start_time = s_line[9]
                    r_line.region = s_line[10]

                    print(f'TEMP – FORUM_FOLDER = {r_line.forum_folder}, while s_line = {str(s_line)}')

                    # case: when new search's status is already not "Ищем" – to be ignored
                    if r_line.status != 'Ищем' and r_line.change_type == 0:  # "new_search":
                        r_line.ignore = 'y'

                    # limit notification sending only for searches started 60 days ago
                    # 60 days – is a compromise and can be reviewed if community votes for another setting
                    try:
                        days_window_for_alerting = 60
                        latest_when_alert = r_line.start_time + datetime.timedelta(days=days_window_for_alerting)
                        if latest_when_alert < datetime.datetime.now():
                            r_line.ignore = 'y'

                            # DEBUG purposes only
                            notify_admin(f'ignoring old search upd {r_line.forum_search_num} '
                                         f'with start time {r_line.start_time}')

                    except: # noqa
                        pass

                    break

        logging.info('New Records enriched from Searches')

    except Exception as e:
        logging.error('Not able to enrich New Records from Searches: ' + str(e))
        logging.exception(e)

    return None


def enrich_new_records_with_search_activities(conn):
    """add to New Records the lists of current searches' activities"""

    global new_records_list

    try:
        list_of_activities = conn.execute("""SELECT sa.search_forum_num, dsa.activity_name from search_activities sa 
        LEFT JOIN dict_search_activities dsa ON sa.activity_type=dsa.activity_id 
        WHERE 
        sa.activity_type <> '9 - hq closed' AND
        sa.activity_type <> '8 - info' AND        
        sa.activity_status = 'ongoing' ORDER BY sa.id; """).fetchall()

        # look for matching Forum Search Numbers in New Records List & Search Activities
        for r_line in new_records_list:
            temp_list_of_activities = []
            for a_line in list_of_activities:
                # when match is found
                if r_line.forum_search_num == a_line[0]:
                    temp_list_of_activities.append(a_line[1])
            r_line.activities = temp_list_of_activities

        logging.info('New Records enriched with Search Activities')

    except Exception as e:
        logging.error('Not able to enrich New Records with Search Activities: ' + str(e))
        logging.exception(e)

    return None


def enrich_new_records_with_managers(conn):
    """add to New Records the lists of current searches' managers"""

    global new_records_list

    try:
        list_of_managers = conn.execute("""
        SELECT search_forum_num, attribute_name, attribute_value 
        FROM search_attributes
        WHERE attribute_name='managers' 
        ORDER BY id; """).fetchall()

        # look for matching Forum Search Numbers in New Records List & Search Managers
        for r_line in new_records_list:
            for m_line in list_of_managers:
                # when match is found
                if r_line.forum_search_num == m_line[0] and m_line[2] != '[]':
                    r_line.managers = m_line[2]

        logging.info('New Records enriched with Managers')

    except Exception as e:
        logging.error('Not able to enrich New Records with Managers: ' + str(e))
        logging.exception(e)

    return None


def enrich_new_records_with_comments(conn, type_of_comments):
    """add to New Records the lists of new comments + new inforg comments"""

    global new_records_list

    try:
        if type_of_comments == 'all':
            comments = conn.execute("""
                                    SELECT 
                                        comment_url, comment_text, comment_author_nickname, comment_author_link, 
                                        search_forum_num, comment_num, comment_global_num
                                    FROM 
                                        comments
                                    WHERE
                                        notification_sent IS NULL
                                    ;""").fetchall()

        elif type_of_comments == 'inforg':
            comments = conn.execute("""
                                    SELECT
                                        comment_url, comment_text, comment_author_nickname, comment_author_link,
                                        search_forum_num, comment_num, comment_global_num
                                    FROM
                                        comments 
                                    WHERE 
                                        notif_sent_inforg IS NULL 
                                        AND LOWER(LEFT(comment_author_nickname,6))='инфорг'
                                    ;""").fetchall()

        else:
            comments = None

        # look for matching Forum Search Numbers in New Records List & Comments
        for r_line in new_records_list:
            if r_line.change_type in {3, 4}:  # {'replies_num_change', 'inforg_replies'}:
                temp_list_of_comments = []
                for c_line in comments:
                    # when match of Forum Numbers is found
                    if r_line.forum_search_num == c_line[4]:
                        # check for empty comments
                        if c_line[1] and c_line[1][0:6].lower() != 'резерв':

                            comment = Comment()
                            comment.comment_url = c_line[0]
                            comment.comment_text = c_line[1]

                            # limitation for extra long messages
                            if len(comment.comment_text) > 3500:
                                comment.comment_text = comment.comment_text[:2000] + '...'

                            comment.comment_author_link = c_line[3]
                            comment.search_forum_num = c_line[4]
                            comment.comment_num = c_line[5]

                            # some nicknames can be like >>Белый<< which crashes html markup -> we delete symbols
                            comment.comment_author_nickname = c_line[2]
                            if comment.comment_author_nickname.find('>') > -1:
                                comment.comment_author_nickname = comment.comment_author_nickname.replace('>', '')
                            if comment.comment_author_nickname.find('<') > -1:
                                comment.comment_author_nickname = comment.comment_author_nickname.replace('<', '')

                            temp_list_of_comments.append(comment)

                if type_of_comments == 'all':
                    r_line.comments = temp_list_of_comments
                elif type_of_comments == 'inforg':
                    r_line.comments_inforg = temp_list_of_comments

        logging.info('New Records enriched with Comments for ' + type_of_comments)

    except Exception as e:
        logging.error('Not able to enrich New Records with Comments for' + type_of_comments + ': ' + str(e))
        logging.exception(e)

    return None


def compose_com_msg_on_new_search(link, name, age, age_wording, activities, managers):
    """compose the common, user-independent message on new search"""

    # 1. List of activities – user-independent
    msg_1 = ''
    if activities:
        for line in activities:
            msg_1 += line + '\n'

    # 2. Person
    age_info = f' {age_wording}' if (name[0].isupper() and age and age != 0) else ''

    msg_2 = f'<a href="{link}">{name}{age_info}</a>'

    # 3. List of managers – user-independent
    msg_3 = ''
    if managers:
        try:
            managers_list = ast.literal_eval(managers)
            msg_3 += 'Ответственные:'
            for manager in managers_list:
                line = add_tel_link(manager)
                msg_3 += '\n &#8226; ' + str(line)

        except Exception as e:
            logging.error('Not able to compose New Search Message text with Managers: ' + str(e))
            logging.exception(e)

    logging.info('msg 2 + msg 1 + msg 3: ' + str(msg_2) + ' // ' + str(msg_1) + ' // ' + str(msg_3))

    return [msg_2, msg_1, msg_3]  # 1 - general, 2 - activities, 3 - managers


def compose_com_msg_on_coords_change(link, name, age, age_wording, new_value):
    """compose the common, user-independent message on coordinates change"""

    age_info = f' {age_wording}' if (name[0].isupper() and age and age != 0) else ''
    # msg = f'Поиск <a href="{link}">{name}{age_info}</a>:\n'
    msg = ''
    lat, lon = None, None
    link_text = '{link_text}'
    region = '{region}'

    # structure: lat, lon, prev_desc, curr_desc
    list_of_coords_changes = ast.literal_eval(new_value)

    verdict = {"drop": False, "add": False, "again": False, 'change': False}
    scenario = None

    for line in list_of_coords_changes:
        if line[2] in {1, 2} and line[3] in {0, 3, 4}:
            verdict['drop'] = True
        elif line[2] == 0 and line[3] in {1, 2}:
            verdict['add'] = True
        elif line[2] in {3, 4} and line[3] in {1, 2}:
            verdict['again'] = True

    if verdict['drop'] and verdict['add']:
        verdict['change'] = True
        verdict['drop'] = False
        verdict['add'] = False

    # A -> B -> A
    if verdict['drop'] and verdict['again']:
        verdict['change'] = True
        verdict['drop'] = False
        verdict['again'] = False

    # TODO: temp try (content is needed, try itself is temp)
    try:
        # CASE 1. Change of coordinates: A -> B
        if verdict['change']:
            msg += f'🧭 Смена координат по <a href="{link}">{name}{age_info}</a> ({region}):\n\nСтарые: '
            for line in list_of_coords_changes:
                if line[2] in {1, 2} and line[3] in {0, 3, 4}:
                    msg += f'{line[0]}, {line[1]}\n'

            msg += '\nНовые:\n'
            for line in list_of_coords_changes:
                if line[2] == 0 and line[3] in {1, 2}:
                    link_text = '{link_text}'
                    clickable_link = generate_yandex_maps_place_link2(line[0], line[1], link_text)
                    msg += f'{clickable_link}\n<code>{line[0]}, {line[1]}</code>\n'
                    lat = line[0]
                    lon = line[1]
                    break

            scenario = 'change'

        # CASE 2. Re-opening of closed coordinates: A -> not-A -> A
        elif verdict['again']:
            msg += f'🧭 Прежние координаты вновь актуальны по <a href="{link}">{name}{age_info}</a> ({region}):\n\n'
            for line in list_of_coords_changes:
                if line[2] in {3, 4} and line[3] in {1, 2}:
                    clickable_link = generate_yandex_maps_place_link2(line[0], line[1], link_text)
                    msg += f'{clickable_link}\n<code>{line[0]}, {line[1]}</code>\n'
                    lat = line[0]
                    lon = line[1]
                    break
            scenario = 'again'

        # CASE 3. Announcement of new coordinates: not-A -> A
        elif verdict['add']:
            msg += f'🧭 Объявлены координаты сбора <a href="{link}">{name}{age_info}</a> ({region}):\n'
            for line in list_of_coords_changes:
                if line[2] == 0 and line[3] in {1, 2}:
                    clickable_link = generate_yandex_maps_place_link2(line[0], line[1], link_text)
                    msg += f'{clickable_link}\n<code>{line[0]}, {line[1]}</code>\n'
                    lat = line[0]
                    lon = line[1]
                    break
            scenario = 'add'

        # CASE 4. Cancellation of announced coordinates: A -> not-A
        elif verdict['drop']:
            msg += f'🧭 Координаты по <a href="{link}">{name}{age_info}</a> ({region}):\n'
            for line in list_of_coords_changes:
                if line[2] in {1, 2} and line[3] in {0, 3, 4}:
                    # clickable_link = generate_yandex_maps_place_link2(line[0], line[1], link_text)
                    # msg += f'{clickable_link}\n'
                    msg += f'Более НЕ АКТУАЛЬНЫ {line[0]}, {line[1]}{link_text}\n'
            scenario = 'drop'

    except Exception as e:
        logging.exception(e)
        msg = f'error{region}{link_text}'

    return msg, lat, lon, scenario


def compose_com_msg_on_field_trip(link, name, age, age_wording, parameters):
    """compose the common, user-independent message on field trips: new, change"""

    parameters = ast.literal_eval(parameters) if parameters else {}

    age_info = f' {age_wording}' if (name[0].isupper() and age and age != 0) else ''
    region = '{region}'  # will be added on level of individual user (some of them see region, some don't)
    direction_and_distance = '{direction_and_distance}'  # will be added on level of individual user (user-specific)

    case = parameters['case']  # scenario of field trip update: None / add / drop / change

    planned = ' планируется' if 'planned' in parameters else ''
    # TODO: probably in urgent and secondary "and parameters['urgent']" is not needed
    urgent = ' срочный' if 'urgent' in parameters and parameters['urgent'] else ''
    secondary = ' повторный' if 'secondary' in parameters and parameters['secondary'] else ''

    date_and_time_curr = f'\n{parameters["date_and_time_curr"]}' if 'date_and_time_curr' in parameters else ''
    address_curr = f'\n{parameters["address_curr"]}' if 'address_curr' in parameters else ''
    coords_list_curr = parameters["coords_curr"] if 'coords_curr' in parameters else None

    date_and_time_prev = f'\n{parameters["date_and_time_prev"]}' if 'date_and_time_prev' in parameters else ''
    address_prev = f'\n{parameters["address_prev"]}' if 'address_prev' in parameters else ''
    coords_list_prev = parameters["coords_prev"] if 'coords_prev' in parameters else None

    if coords_list_curr:
        lat = coordinates_format.format(float(coords_list_curr[0]))
        lon = coordinates_format.format(float(coords_list_curr[1]))
        coords_curr = f'\n<code>{lat}, {lon}</code>'
    else:
        lat, lon = None, None
        coords_curr = ''

    if coords_list_prev:
        lat_prev = coordinates_format.format(float(coords_list_prev[0]))
        lon_prev = coordinates_format.format(float(coords_list_prev[1]))
        coords_prev = f'\n{lat_prev}, {lon_prev}'
    else:
        coords_prev = ''

    if case == 'add':

        msg = f'🚨 Внимание,{urgent}{planned}{secondary} выезд!\n{region}\n\n' \
              f'<a href="{link}">{name}{age_info}</a>\n\n' \
              f'{date_and_time_curr}' \
              f'{address_curr}' \
              f'\n{direction_and_distance}' \
              f'{coords_curr}'

    elif case == 'change':

        msg = f'🚨 Изменения по выезду <a href="{link}">{name}{age_info}</a>\n{region}:\n' \
              f'<del>{date_and_time_prev}' \
              f'{address_prev}' \
              f'{coords_prev}</del>\n' \
              f'{date_and_time_curr}' \
              f'{address_curr}' \
              f'\n{direction_and_distance}' \
              f'{coords_curr}'

    elif case == 'drop':

        msg = f'🚨 Штаб свёрнут – <a href="{link}">{name}{age_info}</a>\n' \
              f'{region}.'

    else:
        msg = None

    # DEBUG
    notify_admin(f'Field Trips / incoming parameters: {parameters}')
    notify_admin(f'Field Trips / Common Message: {msg}')
    # DEBUG

    # Clean the message from excessive line breaks, like \n\n\n. tree repetitions covers majority of cases
    # TODO: to make it more pythonic. it does its' job, but looks ugly
    msg = msg.replace('\n\n\n', '\n\n').replace('\n\n\n', '\n\n').replace('\n\n\n', '\n\n')

    return msg, lat, lon


def compose_com_msg_on_status_change(status, link, name, age, age_wording, region):
    """compose the common, user-independent message on search status change"""

    if status == 'Ищем':
        status_info = 'Поиск возобновлён'
    elif status == 'Завершен':
        status_info = 'Поиск завершён'
    else:
        status_info = status

    age_info = f' {age_wording}' if (name[0].isupper() and age and age != 0) else ''

    msg_1 = f'{status_info} – изменение статуса по <a href="{link}">{name}{age_info}</a>'

    msg_2 = f' ({region})' if region else None

    return msg_1, msg_2


def compose_com_msg_on_new_comments(link, name, age, age_wording, comments):
    """compose the common, user-independent message on ALL search comments change"""

    global new_records_list

    # compose message Header
    age_info = f' {age_wording}' if (name[0].isupper() and age and age != 0) else ''

    prefix_msg = f'Новые комментарии по поиску <a href="{link}">{name}{age_info}</a>:\n'

    # compose a message Body with all the comments
    msg = ''
    for comment in comments:
        if comment.comment_text:
            msg += ' &#8226; <a href="https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='
            msg += str(comment.comment_author_link)
            msg += '">'
            msg += comment.comment_author_nickname
            msg += '</a>: <i>«<a href="'
            msg += comment.comment_url
            msg += '">'
            if len(comment.comment_text) > 1000:
                msg += comment.comment_text[:1000]
            else:
                msg += comment.comment_text
            msg += '</a>»</i>\n'

    if msg:
        msg = prefix_msg + msg

    return msg, None


def compose_com_msg_on_inforg_comments(link, name, age, age_wording, comments, region):
    """compose the common, user-independent message on INFORG search comments change"""

    global new_records_list

    msg_1, msg_2 = None, None
    msg_3 = ''
    if comments:
        author = None
        for comment in comments:
            if comment.comment_text:
                author = '<a href="https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u={}">{}</a>'.format(
                    str(comment.comment_author_link), comment.comment_author_nickname)
                msg_3 += '<i>«<a href="{}">{}</a>»</i>\n'.format(comment.comment_url, comment.comment_text)

        if name[0].isupper() and age and age != 0:
            person = name + ' ' + age_wording
        else:
            person = name

        msg_3 = ':\n' + msg_3

        msg_1 = 'Сообщение от {} по <a href="{}">{}</a>'.format(author, link, person)
        if region:
            msg_2 = ' (' + region + ')'

    return msg_1, msg_2, msg_3


def compose_com_msg_on_title_change(title, link, name, age, age_wording):
    """compose the common, user-independent message on search title change"""

    msg = title
    if msg:
        msg += f' – обновление заголовка поиска по <a href="{link}">{name}'
        if name[0].isupper() and age and age != 0:
            msg += f' {age_wording}'
        msg += '</a>\n'

    return msg


def add_tel_link(incoming_text, modifier='all'):
    """check is text contains phone number and replaces it with clickable version, also removes [tel] tags"""

    outcome_text = None

    # Modifier for all users
    if modifier == 'all':
        outcome_text = incoming_text
        nums = re.findall(r"(?:\+7|7|8)\s?[\s\-(]?\s?\d{3}[\s\-)]?\s?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", incoming_text)
        for num in nums:
            outcome_text = outcome_text.replace(num, '<code>' + str(num) + '</code>')

        phpbb_tags_to_delete = {'[tel]', '[/tel]'}
        for tag in phpbb_tags_to_delete:
            outcome_text = outcome_text.replace(tag, '', 5)

    # Modifier for Admin
    else:
        pass

    return outcome_text


def enrich_new_records_with_com_message_texts():
    """add user-independent message texts to New Records list"""

    global new_records_list

    last_line = None

    try:
        for line in new_records_list:
            last_line = line

            if line.change_type == 0:  # 'new_search':

                start = line.start_time
                now = datetime.datetime.now()
                days_since_search_start = (now - start).days
                # if "old" search - no need to compose & send message
                if days_since_search_start < 2:
                    line.message = compose_com_msg_on_new_search(line.link, line.name, line.age, line.age_wording,
                                                                 line.activities, line.managers)
                else:
                    line.ignore = 'y'

            elif line.change_type == 1:  # 'status_change':
                line.message = compose_com_msg_on_status_change(line.status, line.link, line.name, line.age,
                                                                line.age_wording, line.region)
            elif line.change_type == 2:  # 'title_change':
                line.message = compose_com_msg_on_title_change(line.title, line.link, line.name, line.age,
                                                               line.age_wording)
            elif line.change_type == 3:  # 'replies_num_change':
                line.message = compose_com_msg_on_new_comments(line.link, line.name, line.age, line.age_wording,
                                                               line.comments)
            elif line.change_type == 4:  # 'inforg_replies':
                line.message = compose_com_msg_on_inforg_comments(line.link, line.name, line.age, line.age_wording,
                                                                  line.comments_inforg, line.region)

            elif line.change_type == 5:  # topic_field_trip_new
                # TODO temp debug
                print(f'ZZZ: 1 line.message={line.message}')
                # TODO temp debug
                line.message, line.search_latitude, line.search_longitude = \
                    compose_com_msg_on_field_trip(line.link, line.name, line.age, line.age_wording, line.new_value)

                # TODO temp debug
                print(f'ZZZ: 2 line.message={line.message}')
                # TODO temp debug

            elif line.change_type == 6:  # topic_field_trip_change
                line.message, line.search_latitude, line.search_longitude = \
                    compose_com_msg_on_field_trip(line.link, line.name, line.age, line.age_wording, line.new_value)

            # TODO: temp
            elif line.change_type == 7:  # coords_change
                line.message, line.search_latitude, line.search_longitude, line.coords_change_type = \
                    compose_com_msg_on_coords_change(line.link, line.name, line.age, line.age_wording, line.new_value)

        logging.info('New Records enriched with common Message Texts')

    except Exception as e:
        logging.error('Not able to enrich New Records with common Message Texts:' + str(e))
        logging.exception(e)
        logging.info('FOR DEBUG OF ERROR – line is: ' + str(last_line))

    return None


def compose_users_list_from_users(conn):
    """compose the Users list from the tables Users & User Coordinates: one Record = one user"""

    global users_list

    try:
        users = conn.execute(
            """SELECT ns.*, st.num_of_new_search_notifs FROM 
            (SELECT u.user_id, u.username_telegram, uc.latitude, uc.longitude, u.role FROM users as u 
            LEFT JOIN 
            user_coordinates as uc ON u.user_id=uc.user_id 
            WHERE u.status = 'unblocked' or u.status is Null) ns 
            LEFT JOIN 
            user_stat st ON ns.user_id=st.user_id;"""
        ).fetchall()

        for line in users:
            new_line = User(user_id=line[0], username_telegram=line[1], user_latitude=line[2], user_longitude=line[3],
                            user_role=line[4])
            if line[5] == 'None' or line[5] is None:
                new_line.user_new_search_notifs = 0
            else:
                new_line.user_new_search_notifs = int(line[5])

            users_list.append(new_line)

        logging.info('User List composed')
        # logging.info('User List: ' + str(users_list))

    except Exception as e:
        logging.error('Not able to compose Users List: ' + repr(e))
        logging.exception(e)

    return None


def enrich_users_list_with_age_periods(conn):
    """add the data on Lost people age notification preferences from user_pref_age into users List"""

    global users_list

    try:
        notif_prefs = conn.execute("""SELECT user_id, period_min, period_max FROM user_pref_age;""").fetchall()

        if not notif_prefs:
            return None

        # convert the received list into one list
        for np_line in notif_prefs:
            new_period = [np_line[1], np_line[2]]
            for u_line in users_list:
                if u_line.user_id == np_line[0]:
                    u_line.age_periods.append(new_period)

        logging.info('Users List enriched with Age Prefs')

    except Exception as e:
        logging.info(f'Not able to enrich Users List with Age Prefs')
        logging.exception(e)

    return None


def enrich_users_list_with_notification_preferences(conn):
    """add the additional data on notification preferences from User_preferences into Users List"""

    global users_list

    try:
        notif_prefs = conn.execute(
            """SELECT user_id, preference, pref_id FROM user_preferences;"""
        ).fetchall()

        # look for matching User_ID in Users List & Notification Preferences
        for u_line in users_list:
            prefs_array = []
            user_pref_ids_list = []
            for np_line in notif_prefs:
                # when match is found
                if u_line.user_id == np_line[0]:
                    prefs_array.append(np_line[1])
                    user_pref_ids_list.append(np_line[2])

            u_line.notification_preferences = prefs_array
            u_line.notif_pref_ids_list = user_pref_ids_list

        logging.info('Users List enriched with Notification Prefs')

    except Exception as e:
        logging.error('Not able to enrich Users List with Notification Prefs: ' + str(e))
        logging.exception(e)

    return None


def enrich_users_list_with_user_regions(conn):
    """add the additional data on user preferred regions from User Regional Preferences into Users List"""

    global users_list

    try:
        reg_prefs = conn.execute(
            """SELECT user_id, forum_folder_num FROM user_regional_preferences;"""
        ).fetchall()

        # look for matching User_ID in Users List & Regional Preferences
        for u_line in users_list:
            prefs_array = []
            for rp_line in reg_prefs:
                # when match is found
                if u_line.user_id == rp_line[0]:
                    prefs_array.append(rp_line[1])

            u_line.user_regions = prefs_array

            if len(prefs_array) < 2:
                u_line.user_in_multi_regions = False

        logging.info('Users List enriched with User Regions')

    except Exception as e:
        logging.error('Not able to enrich Users List with User Regions: ' + repr(e))
        logging.exception(e)

    return None


def get_list_of_admins_and_testers(conn):
    """get the list of users with admin & testers roles from PSQL"""

    list_of_admins = []
    list_of_testers = []

    try:
        user_roles = conn.execute(
            """SELECT user_id, role FROM user_roles;"""
        ).fetchall()

        for line in user_roles:
            if line[1] == 'admin':
                list_of_admins.append(line[0])
            elif line[1] == 'tester':
                list_of_testers.append(line[0])

        logging.info('Got the Lists of Admins & Testers')

    except Exception as e:
        logging.info('Not able to get the lists of Admins & Testers ')
        logging.exception(e)

    return list_of_admins, list_of_testers


def record_notification_statistics(conn):
    """records +1 into users' statistics of new searches notification. needed only for usability tips"""

    global stat_list_of_recipients

    dict_of_user_and_number_of_new_notifs = {i: stat_list_of_recipients.count(i) for i in stat_list_of_recipients}

    try:
        for user_id in dict_of_user_and_number_of_new_notifs:
            number_to_add = dict_of_user_and_number_of_new_notifs[user_id]

            sql_text = sqlalchemy.text("""
            INSERT INTO user_stat (user_id, num_of_new_search_notifs) 
            VALUES(:a, :b)
            ON CONFLICT (user_id) DO 
            UPDATE SET num_of_new_search_notifs = :b + 
            (SELECT num_of_new_search_notifs from user_stat WHERE user_id = :a) 
            WHERE user_stat.user_id = :a;
            """)
            conn.execute(sql_text, a=int(user_id), b=int(number_to_add))

    except Exception as e:
        logging.error('Recording statistics in notification script failed' + repr(e))
        logging.exception(e)

    return None


def iterate_over_all_users_and_updates(conn):
    """initiates a full cycle for all messages send to all the users"""

    def save_to_sql_notif_by_user(mailing_id_, user_id_, message_, message_without_html_,
                                  message_type_, message_params_, message_group_id_, change_log_id_):
        """save to sql table notif_by_user the new message"""

        # record into SQL table notif_by_user
        sql_text_ = sqlalchemy.text("""
                            INSERT INTO notif_by_user (
                                mailing_id, 
                                user_id, 
                                message_content, 
                                message_text, 
                                message_type, 
                                message_params,
                                message_group_id,
                                change_log_id,
                                created) 
                            VALUES (:a, :b, :c, :d, :e, :f, :g, :h, :i);
                            """)

        conn.execute(sql_text_,
                     a=mailing_id_,
                     b=user_id_,
                     c=message_,
                     d=message_without_html_,
                     e=message_type_,
                     f=message_params_,
                     g=message_group_id_,
                     h=change_log_id_,
                     i=datetime.datetime.now()
                     )

        return None

    def get_from_sql_if_was_notified_already(user_id_, message_type_, change_log_id_):
        """check in sql if this user was already notified re this change_log record
        works for every user during iterations over users"""

        sql_text_ = sqlalchemy.text("""
            SELECT EXISTS (
                SELECT 
                    message_id 
                FROM 
                    notif_by_user 
                WHERE 
                    completed IS NOT NULL AND
                    user_id=:b AND 
                    message_type=:c AND
                    change_log_id=:a
            )
            /*action='get_from_sql_if_was_notified_already_new'*/
            ;
        """)

        user_was_already_notified = conn.execute(sql_text_,
                                                 a=change_log_id_,
                                                 b=user_id_,
                                                 c=message_type_
                                                 ).fetchone()[0]

        return user_was_already_notified

    def get_from_sql_list_of_already_notified_users(change_log_id_):
        """check in sql if this user was already notified for this change_log record
        works one time only, prior to iteration over users"""

        sql_text_ = sqlalchemy.text("""
            SELECT 
                user_id 
            FROM 
                notif_by_user 
            WHERE 
                completed IS NOT NULL AND
                change_log_id=:a
                    
            /*action='get_from_sql_list_of_already_notified_users 2.0'*/
            ;
            """)

        raw_data_ = conn.execute(sql_text_, a=change_log_id_).fetchall()
        # TODO: to delete
        logging.info("DDD: NEW: were notified:")
        logging.info(raw_data_)

        users_who_were_notified = []
        for line in raw_data_:
            users_who_were_notified.append(line[0])

        return users_who_were_notified

    def get_the_new_group_id():
        """define the max message_group_id in notif_by_user and add +1"""

        raw_data_ = conn.execute("""SELECT MAX(message_group_id) FROM notif_by_user
        /*action='get_the_new_group_id'*/
        ;""").fetchone()

        if raw_data_[0]:
            next_id = raw_data_[0] + 1
        else:
            next_id = 0

        return next_id

    def process_mailing_id(change_log_item):
        """TODO"""

        # check if this change_log record was somehow processed
        sql_text = sqlalchemy.text("""SELECT EXISTS (SELECT * FROM notif_mailings WHERE change_log_id=:a);""")
        record_was_processed_already = conn.execute(sql_text, a=change_log_item).fetchone()[0]

        # TODO: DEBUG
        if record_was_processed_already:
            logging.info('[comp_notif]: 2 MAILINGS for 1 CHANGE LOG RECORD identified')
        # TODO: DEBUG

        # record into SQL table notif_mailings
        sql_text = sqlalchemy.text("""
                        INSERT INTO notif_mailings (topic_id, source_script, mailing_type, change_log_id) 
                        VALUES (:a, :b, :c, :d)
                        RETURNING mailing_id;
                        """)
        raw_data = conn.execute(sql_text,
                                a=topic_id,
                                b='notifications_script',
                                c=change_type,
                                d=change_log_item
                                ).fetchone()

        mail_id = raw_data[0]
        logging.info(f'mailing_id = {mail_id}')

        users_should_not_be_informed = get_from_sql_list_of_already_notified_users(change_log_item)
        logging.info('users_who_should_not_be_informed:')
        logging.info(users_should_not_be_informed)
        logging.info('in total ' + str(len(users_should_not_be_informed)))

        # TODO: do we need this table at all?
        # record into SQL table notif_mailings_status
        sql_text = sqlalchemy.text("""
                                            INSERT INTO notif_mailing_status (mailing_id, event, event_timestamp) 
                                            VALUES (:a, :b, :c);
                                            """)
        conn.execute(sql_text,
                     a=mail_id,
                     b='created',
                     c=datetime.datetime.now())

        return users_should_not_be_informed, record_was_processed_already, mail_id

    def crop_user_list(users_list_incoming, users_should_not_be_informed, record):
        """crop user_list to only affected users"""

        # crop the list of users, excluding Users who were already notified on this change_log_id
        temp_user_list = []
        for user_line in users_list_incoming:
            if user_line.user_id not in users_should_not_be_informed:
                temp_user_list.append(user_line)
        logging.info(f'User List crop due to doubling: {len(users_list_incoming)} --> {len(temp_user_list)}')
        users_list_outcome = temp_user_list

        # crop the list of users, excluding Users from other regions
        temp_user_list = []
        for user_line in users_list_outcome:
            for region_line in user_line.user_regions:
                if str(region_line) == str(record.forum_folder):
                    temp_user_line = user_line
                    # temp_user_line.user_regions = str(region_line)
                    temp_user_list.append(temp_user_line)
        logging.info(f'User List crop due to region: {len(users_list_outcome)} --> {len(temp_user_list)}')
        users_list_outcome = temp_user_list

        return users_list_outcome

    global new_records_list
    global users_list
    global coordinates_format
    global stat_list_of_recipients

    stat_list_of_recipients = []  # still not clear why w/o it – saves data from prev iterations
    number_of_situations_checked = 0
    number_of_messages_sent = 0
    cleaner = re.compile('<.*?>')

    try:

        # execute new updates one-by-one
        for new_record in new_records_list:

            # skip ignored lines which don't require a notification
            if new_record.ignore != 'y':

                # TODO: temp debug
                admins_list, testers_list = get_list_of_admins_and_testers(conn)
                # TODO: temp debug

                s_lat = new_record.search_latitude
                s_lon = new_record.search_longitude
                topic_id = new_record.forum_search_num
                change_type = new_record.change_type
                change_log_id = new_record.change_id

                users_who_should_not_be_informed, this_record_was_processed_already, mailing_id = \
                    process_mailing_id(change_log_id)

                # TODO – if works smoothly – to utilize it further
                new_user_list = crop_user_list(users_list, users_who_should_not_be_informed, new_record)
                # TODO ^^^

                for user in users_list:
                    print(f'TEMP - we are in USERS, user = {user}')
                    u_lat = user.user_latitude
                    u_lon = user.user_longitude
                    user_notif_pref_ids_list = user.notif_pref_ids_list
                    user_reg_prefs = user.user_regions

                    # as user can have multi-reg preferences – check every region
                    for region in user_reg_prefs:
                        print(f'TEMP - we are in USERS / REGIONS, user = {user}, region = {region}')
                        print(f'TEMP - new_record.forum_folder = {new_record.forum_folder}')

                        if str(region) == str(new_record.forum_folder):
                            print(f'TEMP - we are in USERS / REGIONS / REG MATCH, user = {user}, '
                                  f'region = {region}, cl_reg = {new_record.forum_folder}')

                            region_to_show = None
                            if user.user_in_multi_regions:
                                region_to_show = new_record.region

                            # as user can have several notification preferences – check every preference
                            # for notif_pref in user_notif_prefs:
                            for user_notif_pref_id in user_notif_pref_ids_list:

                                print(f'TEMP - we are in USERS / REGIONS / REG MATCH / PREF, user = {user}, '
                                      f'region = {region}, pref_id = {user_notif_pref_id}')

                                # check if user wants to receive this kind of notifications

                                # TODO: temp limitation for ones who have 5 or 6 or 7
                                # if this is a mailing that users wants to receive
                                if user_notif_pref_id == change_type or \
                                        (user_notif_pref_id == 30 and change_type not in {5, 6, 7}):  # 30 = 'all'

                                    print(f'TEMP - we are in USERS / REGIONS / REG MATCH / PREF / PREF MATCH, '
                                          f'user = {user}, '
                                          f'region = {region}, pref_id = {user_notif_pref_id}, '
                                          f'cl_pref = {change_type}')

                                    # on this step - we're certain: user should receive the notification
                                    # compose the notification
                                    message = ''
                                    number_of_situations_checked += 1

                                    # start composing individual messages (specific user on specific situation)
                                    if change_type == 0:  # new_search
                                        num_of_msgs_sent_already = user.user_new_search_notifs
                                        message = compose_individual_message_on_new_search(new_record, s_lat, s_lon,
                                                                                           u_lat, u_lon,
                                                                                           region_to_show,
                                                                                           num_of_msgs_sent_already)
                                    elif change_type == 1:  # status_change
                                        message = new_record.message[0]
                                        if user.user_in_multi_regions and new_record.message[1]:
                                            message += new_record.message[1]

                                    elif change_type == 2:  # 'title_change':
                                        message = new_record.message

                                    elif change_type == 3:  # 'replies_num_change':
                                        message = new_record.message[0]

                                    elif change_type == 4:  # 'inforg_replies':
                                        message = new_record.message[0]
                                        if user.user_in_multi_regions and new_record.message[1]:
                                            message += new_record.message[1]
                                        if new_record.message[2]:
                                            message += new_record.message[2]

                                    elif change_type == 5:  # field_trips_new

                                        # TODO: temp limitation for ADMIN
                                        if user.user_id in admins_list:
                                            message = compose_individual_msg_on_field_trip(new_record.message,
                                                                                           s_lat, s_lon,
                                                                                           u_lat, u_lon,
                                                                                           region_to_show)

                                    elif change_type == 6:  # field_trips_change

                                        # TODO: temp limitation for ADMIN
                                        if user.user_id in admins_list:
                                            message = compose_individual_msg_on_field_trip(new_record.message,
                                                                                           s_lat, s_lon,
                                                                                           u_lat, u_lon,
                                                                                           region_to_show)

                                    elif change_type == 7:  # coords_change
                                        # TODO: temp debug
                                        print(f'YYY: user_id={user.user_id}, user={user}, '
                                              f'prefs={user_notif_pref_ids_list}')
                                        # TODO: temp debug

                                        # TODO: temp limitation for ADMIN
                                        if user.user_id in admins_list:
                                            message = compose_individual_message_on_coords_change(new_record, s_lat,
                                                                                                  s_lon, u_lat,
                                                                                                  u_lon,
                                                                                                  region_to_show)

                                    # TODO: to delete msg_group at all
                                    # messages followed by coordinates (sendMessage + sendLocation) have same group
                                    msg_group_id = get_the_new_group_id() if change_type in {0, 5, 6, 7} else None
                                    # not None for new_search, field_trips_new, field_trips_change,  coord_change

                                    # define if user received this message already
                                    this_user_was_notified = False
                                    if this_record_was_processed_already:
                                        this_user_was_notified = get_from_sql_if_was_notified_already(
                                            user.user_id, 'text', new_record.change_id)

                                        # logging block
                                        logging.info('this user was notified already {}, {}'.format(
                                            user.user_id, this_user_was_notified))
                                        if user.user_id in users_who_should_not_be_informed:
                                            logging.info('this user is in the list of non-notifiers')
                                        else:
                                            logging.info('this user is NOT in the list of non-notifiers')

                                    if message and not this_user_was_notified:

                                        # TODO: make text more compact within 50 symbols
                                        message_without_html = re.sub(cleaner, '', message)

                                        message_params = {'parse_mode': 'HTML',
                                                          'disable_web_page_preview': 'True'}

                                        # TODO: Debug only - to delete
                                        print(f'what we are saving to SQL: {mailing_id}, {user.user_id}, '
                                              f'{message_without_html}, {message_params}, {msg_group_id},'
                                              f'{change_log_id}')
                                        # TODO: Debug only - to delete

                                        # record into SQL table notif_by_user
                                        save_to_sql_notif_by_user(mailing_id, user.user_id,
                                                                  message,
                                                                  message_without_html,
                                                                  'text',
                                                                  message_params, msg_group_id,
                                                                  change_log_id)

                                        # for user tips in "new search" notifs – to increase sent messages counter
                                        if change_type == 0:  # 'new_search':
                                            stat_list_of_recipients.append(user.user_id)

                                        # save to SQL the sendLocation notification for "new search" & "field trips"
                                        if change_type in {0, 5, 6} and s_lat and s_lon:
                                            # 'new_search', field_trip_new, field_trip_change
                                            message_params = {'latitude': s_lat,
                                                              'longitude': s_lon}

                                            # record into SQL table notif_by_user (not text, but coords only)
                                            save_to_sql_notif_by_user(mailing_id, user.user_id,
                                                                      None,
                                                                      None, 'coords',
                                                                      message_params,
                                                                      msg_group_id,
                                                                      change_log_id)

                                        # save to SQL the sendLocation notification for "coords change"
                                        if change_type == 7 and s_lat and s_lon \
                                                and new_record.coords_change_type != 'drop' \
                                                and user.user_id in admins_list:  # coords_change
                                            message_params = {'latitude': s_lat,
                                                              'longitude': s_lon}

                                            save_to_sql_notif_by_user(mailing_id, user.user_id,
                                                                      None,
                                                                      None, 'coords',
                                                                      message_params,
                                                                      msg_group_id,
                                                                      change_log_id)

                                        number_of_messages_sent += 1

                # mark this line as all-processed
                new_record.processed = 'yes'

            # mark all ignored lines as processed
            else:
                new_record.processed = 'yes'

        logging.info('Iterations over all Users and Updates are done')

    except Exception as e1:
        logging.info('Not able to Iterate over all Users and Updates: ')
        logging.exception(e1)

    return None


def generate_yandex_maps_place_link2(lat, lon, param):
    """generate a link to yandex map with lat/lon"""

    display = 'Карта' if param == 'map' else param
    msg = f'<a href="https://yandex.ru/maps/?pt={lon},{lat}&z=11&l=map">{display}</a>'

    return msg


def compose_individual_message_on_new_search(new_record, s_lat, s_lon, u_lat, u_lon, region_to_show, num_of_sent):
    """compose individual message for notification of every user on new search"""

    # 0. Heading and Region clause if user is 'multi-regional'

    region_wording = f' в регионе {region_to_show}' if region_to_show else ''
    message = f'Новый поиск{region_wording}!\n'

    # 1. Search important attributes - common part (e.g. 'Внимание, выезд!)
    if new_record.message[1]:
        message += new_record.message[1]

    # 2. Person (e.g. 'Иванов 60' )
    message += '\n' + new_record.message[0]

    # 3. Dist & Dir – individual part for every user
    if s_lat and s_lon and u_lat and u_lon:
        try:
            dist, direct = define_dist_and_dir_to_search(s_lat, s_lon, u_lat, u_lon)
            direction = f'\n\nОт вас ~{dist} км {direct}'

            message += generate_yandex_maps_place_link2(s_lat, s_lon, direction)
            message += f'\n<code>{coordinates_format.format(float(s_lat))}, ' \
                       f'{coordinates_format.format(float(s_lon))}</code>'

        except Exception as e:
            logging.info(f'Not able to compose individual msg with distance & direction, params: '
                         f'[{new_record}, {s_lat}, {s_lon}, {u_lat}, {u_lon}]')
            logging.exception(e)

    if s_lat and s_lon and not u_lat and not u_lon:
        try:
            message += '\n\n' + generate_yandex_maps_place_link2(s_lat, s_lon, 'map')

        except Exception as e:
            logging.info(f'Not able to compose message with Yandex Map Link, params: '
                         f'[{new_record}, {s_lat}, {s_lon}, {u_lat}, {u_lon}]')
            logging.exception(e)

    # 4. Managers – common part
    if new_record.message[2]:
        message += '\n\n' + new_record.message[2]

    message += '\n\n'

    # 5. Tips and Suggestions
    if not num_of_sent or num_of_sent in fib_list:
        if s_lat and s_lon:
            message += '<i>Совет: Координаты и телефоны можно скопировать, ' \
                       'нажав на них.</i>\n'

        if s_lat and s_lon and not u_lat and not u_lon:
            message += '<i>Совет: Чтобы Бот показывал Направление и Расстояние' \
                       ' до поиска – просто укажите ваши "Домашние координаты" ' \
                       'в Настройках Бота.</i>'

    return message


def compose_individual_msg_on_field_trip(common_message, s_lat, s_lon, u_lat, u_lon, region_to_show):
    """compose individual message for notification of every user on new field trip"""

    # for reference, the below is the structure of common message
    """com_msg = f'🚨 Внимание, (urgent)(now)(secondary) выезд!\n' \
          f'Поиск <a href="(link)">(name)(age_info)</a>{region}:\n\n' \
          f'(date_and_time_curr)(address_curr)' \
          f'{direction_and_distance}' \
          f'(coords)'"""

    # the list of parameters to be defined on user-level:
    region = f'{region_to_show}' if region_to_show else ''
    if s_lat and s_lon and u_lat and u_lon:
        dist, direct = define_dist_and_dir_to_search(s_lat, s_lon, u_lat, u_lon)
        direction_wording = f'От вас ~{dist} км {direct}'
        direction_and_distance = generate_yandex_maps_place_link2(s_lat, s_lon, direction_wording)

    elif s_lat and s_lon and not u_lat and not u_lon:
        direction_and_distance = generate_yandex_maps_place_link2(s_lat, s_lon, 'map')

    else:
        direction_and_distance = ''

    # taking the common message and injecting individual user-related parameters
    individual_message = common_message.format(region=region, direction_and_distance=direction_and_distance)

    return individual_message


def compose_individual_message_on_coords_change(new_record, s_lat, s_lon, u_lat, u_lon, region_to_show):
    """compose individual message for notification of every user on change of coordinates"""

    msg = new_record.message

    region = f'{region_to_show}' if region_to_show else ''
    link_text = f'{s_lat}, {s_lon}' if new_record.coords_change_type != 'drop' else ''

    if s_lat and s_lon and u_lat and u_lon:
        dist, direct = define_dist_and_dir_to_search(s_lat, s_lon, u_lat, u_lon)
        link_text = f'От вас ~{dist} км {direct}'

    msg = msg.format(region=region, link_text=link_text)

    return msg


def publish_to_pubsub(topic_name, message):
    """publish a new message to pub/sub"""

    global project_id

    topic_path = publisher.topic_path(project_id, topic_name)
    message_json = json.dumps({'data': {'message': message}, })
    message_bytes = message_json.encode('utf-8')

    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publishing succeeded
        logging.info(f'Sent pub/sub message: {message}')

    except Exception as e:
        logging.info('Not able to send pub/sub message: ')
        logging.exception(e)

    return None


def notify_admin(message):
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub('topic_notify_admin', message)

    return None


def mark_new_records_as_processed(conn):
    """mark all the new records in SQL as processed, to avoid processing in the next iteration"""

    try:
        # Compose the list of Change_log id's for which notifications were sent, hence which to be marked as 'processed'
        change_id_list = []
        change_id_list_ignored = []

        for record in new_records_list:

            if record.processed == 'yes':
                if record.ignore != 'y':
                    change_id_list.append(record.change_id)
                else:
                    change_id_list_ignored.append(record.change_id)

        for record in change_id_list:
            sql_text = sqlalchemy.text("""UPDATE change_log SET notification_sent = 'y' WHERE id=:a;""")
            conn.execute(sql_text, a=record)

        for record in change_id_list_ignored:
            sql_text = sqlalchemy.text("""UPDATE change_log SET notification_sent = 'n' WHERE id=:a;""")
            conn.execute(sql_text, a=record)

        logging.info(f'The list of Updates that are processed and not ignored: {change_id_list}')
        logging.info(f'The list of Updates that are processed and ignored: {change_id_list_ignored}')
        logging.info('All Updates are marked as processed in Change Log')

    except Exception as e:

        # For Safety's Sake – Update Change_log SQL table, setting 'y' everywhere
        conn.execute(
            """UPDATE change_log SET notification_sent = 'y' WHERE notification_sent is NULL 
            OR notification_sent='s';"""
        )

        logging.info('Not able to mark Updates as Processed in Change Log')
        logging.exception(e)
        logging.info('Due to error, all Updates are marked as processed in Change Log')
        notify_admin('ERROR: Not able to mark Updates as Processed in Change Log!')

    return None


def mark_new_comments_as_processed(conn):
    """mark in SQL table Comments all the comments that were processed at this step, basing on search_forum_id"""

    try:
        change_id_list_all = []
        change_id_list_inforg = []
        for record in new_records_list:
            if record.processed == 'yes' and record.change_type == 3 and record.ignore != 'y':
                change_id_list_all.append(record.forum_search_num)
            elif record.processed == 'yes' and record.change_type == 4 and record.ignore != 'y':
                change_id_list_inforg.append(record.forum_search_num)

        for record in change_id_list_all:
            sql_text = sqlalchemy.text("UPDATE comments SET notification_sent = 'y' WHERE search_forum_num=:a;")
            conn.execute(sql_text, a=record)

        for record in change_id_list_inforg:
            sql_text = sqlalchemy.text("UPDATE comments SET notif_sent_inforg = 'y' WHERE search_forum_num=:a;")
            conn.execute(sql_text, a=record)

        logging.info(f'The list of Updates with Comments that are processed and not ignored: {change_id_list_all}, '
                     f'{change_id_list_inforg}')
        logging.info('All Comments are marked as processed')

    except Exception as e:

        sql_text = sqlalchemy.text("""UPDATE comments SET notification_sent = 'y' WHERE notification_sent is Null 
                                        OR notification_sent = 's';""")
        conn.execute(sql_text)
        sql_text = sqlalchemy.text("""UPDATE comments SET notif_sent_inforg = 'y' WHERE notif_sent_inforg is Null 
                                        ;""")
        conn.execute(sql_text)

        logging.info('Not able to mark Comments as Processed:')
        logging.exception(e)
        logging.info('Due to error, all Comments are marked as processed')
        notify_admin('ERROR: Not able to mark Comments as Processed!')

    return None


def check_and_save_event_id(context, event, conn):
    """Work with PSQL table notif_functions_registry. Goal of the table & function is to avoid parallel work of
    two compose_notifications functions. Executed in the beginning and in the end of compose_notifications function"""

    def check_if_other_functions_are_working():
        """Check in PSQL in there's the same function 'compose_notifications' working in parallel"""

        sql_text_psy = sqlalchemy.text("""
                        SELECT 
                            event_id 
                        FROM
                            notif_functions_registry
                        WHERE
                            time_start > NOW() - interval '130 seconds' AND
                            time_finish IS NULL AND
                            cloud_function_name  = 'compose_notifications'
                        ;
                        /*action='check_if_there_is_parallel_compose_function' */
                        ;""")

        lines = conn.execute(sql_text_psy).fetchone()

        parallel_functions = True if lines else False

        return parallel_functions

    def record_start_of_function(event_num):
        """Record into PSQL that this function started working (id = id of the respective pub/sub event)"""

        sql_text_psy = sqlalchemy.text("""
                        INSERT INTO 
                            notif_functions_registry
                        (event_id, time_start, cloud_function_name)
                        VALUES
                        (:a, :b, :c);
                        /*action='save_start_of_compose_function' */
                        ;""")

        conn.execute(sql_text_psy, a=event_id, b=datetime.datetime.now(), c='compose_notifications')
        logging.info(f'function was triggered by event {event_num}')

        return None

    def record_finish_of_function(event_num):
        """Record into PSQL that this function finished working (id = id of the respective pub/sub event)"""

        sql_text_psy = sqlalchemy.text("""
                        UPDATE 
                            notif_functions_registry
                        SET
                            time_finish = :a
                        WHERE
                            event_id = :b
                        ;
                        /*action='save_finish_of_compose_function' */
                        ;""")

        conn.execute(sql_text_psy, a=datetime.datetime.now(), b=event_num)

        return None

    if not context or not event:
        return False

    try:
        event_id = context.event_id
    except Exception as e:  # noqa
        return False

    # if this functions is triggered in the very beginning of the Google Cloud Function execution
    if event == 'start':
        if check_if_other_functions_are_working():
            record_start_of_function(event_id)
            return True

        record_start_of_function(event_id)
        return False

    # if this functions is triggered in the very end of the Google Cloud Function execution
    elif event == 'finish':
        record_finish_of_function(event_id)
        return False


def main(event, context):  # noqa
    """key function which is initiated by Pub/Sub"""

    global new_records_list
    global users_list

    # TODO: should be avoided in the future (doesn't return None help?)
    # the below two lines are required - in other case these arrays are not always empty,
    # spent 2 hours - don't know why using '=[]' in the body of this Script (lines ~14-15) is not sufficient
    new_records_list = []
    users_list = []

    # initiate SQL connection
    pool = sql_connect()
    with pool.connect() as conn:

        there_is_function_working_in_parallel = check_and_save_event_id(context, 'start', conn)
        if there_is_function_working_in_parallel:
            logging.info(f'function execution stopped due to parallel run with another function')
            check_and_save_event_id(context, 'finish', conn)
            logging.info('script finished')
            conn.close()
            pool.dispose()
            return None

        # compose New Records List: the delta from Change log
        compose_new_records_from_change_log(conn)

        # only if there are updates in Change Log
        if new_records_list:
            # enrich New Records List with all the updates that should be in notifications
            enrich_new_records_from_searches(conn)
            enrich_new_records_with_search_activities(conn)
            enrich_new_records_with_managers(conn)
            enrich_new_records_with_comments(conn, 'all')
            enrich_new_records_with_comments(conn, 'inforg')
            enrich_new_records_with_com_message_texts()

            # compose Users List: all the notifications recipients' details
            compose_users_list_from_users(conn)
            enrich_users_list_with_notification_preferences(conn)
            enrich_users_list_with_age_periods(conn)
            enrich_users_list_with_user_regions(conn)

            # check the matrix: new update - user and initiate sending notifications
            iterate_over_all_users_and_updates(conn)

            # mark all the "new" lines in tables Change Log & Comments as "old"
            mark_new_records_as_processed(conn)
            mark_new_comments_as_processed(conn)

            # final step – update statistics on how many users received notifications on new searches
            record_notification_statistics(conn)

        # check if there are any notifications remained to be composed
        check = conn.execute(
            """
            SELECT search_forum_num, changed_field, new_value, id, change_type FROM change_log 
            WHERE notification_sent is NULL 
            OR notification_sent='s' LIMIT 1; """
        ).fetchall()
        if check:
            logging.info('we checked – there is still something to notify, so we re-initiated this function')
            publish_to_pubsub('topic_for_notification', 're-run from same script')

        check_and_save_event_id(context, 'finish', conn)
        publish_to_pubsub('topic_to_send_notifications', 'initiate notifs send out')
        logging.info('script finished')

        conn.close()
    pool.dispose()

    del new_records_list
    del users_list

    return None
