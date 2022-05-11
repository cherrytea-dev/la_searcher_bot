import os
import base64

import ast
import re
import datetime
import json
import logging
import math
import time

from telegram import Bot  # TODO: probably to move to aiogram? or mtproto?

import sqlalchemy  # TODO: to switch to psycopg2? probably not, due to SQL injection safety

from google.cloud import secretmanager
from google.cloud import pubsub_v1
# TODO: to migrate to 3.9 python


project_id = os.environ["GCP_PROJECT"]
gcp_function_name = os.environ["FUNCTION_NAME"]
client = secretmanager.SecretManagerServiceClient()
publisher = pubsub_v1.PublisherClient()
db = None
new_records_list = []
users_list = []
coordinates_format = "{0:.5f}"
stat_list_of_recipients = []  # list of users who received notification on new search
fib_list = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]

# TODO: temp
trigg = 0

# for analytics
analytics_notif_times = []
srch_id = None
chng_id = None
chng_type = None
mailing_id = None
script_start_time = None


def sql_connect():
    db_user = get_secrets("cloud-postgres-username")
    db_pass = get_secrets("cloud-postgres-password")
    db_name = get_secrets("cloud-postgres-db-name")
    db_conn = get_secrets("cloud-postgres-connection-name")
    db_socket_dir = "/cloudsql"
    db_config = {
        "pool_size": 30,
        "max_overflow": 0,
        "pool_timeout": 10,  # seconds
        "pool_recycle": 0,  # seconds
    }
    try:
        pool = sqlalchemy.create_engine(
            sqlalchemy.engine.url.URL(
                drivername="postgresql+pg8000",
                username=db_user,
                password=db_pass,
                database=db_name,
                query={
                    "unix_sock": "{}/{}/.s.PGSQL.5432".format(
                        db_socket_dir,
                        db_conn)
                }
            ),
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
        # it happens when first two wither Найден Жив or Найден Погиб with different word forms
        if string_by_word[0][0:4].lower() == "найд":
            fam_name = string_by_word[2]

        # case when "Поиск приостановлен"
        elif string_by_word[1][0:8].lower() == 'приостан':
            fam_name = string_by_word[2]

        # all other cases
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
    dlon = lon2 - lon1

    dlat = lat2 - lat1

    # Haversine formula
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = earth_radius * c
    dist = round(distance)

    # define direction

    def calc_bearing(lat_2, lon_2, lat_1, lon_1):
        d_lon = (lon_2 - lon_1)
        x = math.cos(math.radians(lat_2)) * math.sin(math.radians(d_lon))
        y = math.cos(math.radians(lat_1)) * math.sin(math.radians(lat_2)) - math.sin(math.radians(lat_1)) * math.cos(
            math.radians(lat_2)) * math.cos(math.radians(d_lon))
        bearing = math.atan2(x, y)  # use atan2 to determine the quadrant
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
                 ignore=None
                 ):
        self.comment_url = comment_url
        self.comment_text = comment_text
        self.comment_author_nickname = comment_author_nickname
        self.comment_author_link = comment_author_link
        self.search_forum_num = search_forum_num
        self.comment_num = comment_num
        self.ignore = ignore

    def __str__(self):
        return str([self.comment_url, self.comment_text, self.comment_author_nickname, self.comment_author_link,
                    self.search_forum_num, self.comment_num, self.ignore])


class LineInChangeLog:
    def __init__(self,
                 forum_search_num=None,
                 change_type=None,
                 changed_field=None,
                 changed_field_for_user=None,
                 change_id=None,
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
                 region=None
                 ):
        self.forum_search_num = forum_search_num
        self.change_type = change_type
        self.changed_field = changed_field
        self.changed_field_for_user = changed_field_for_user
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

    def __str__(self):
        return str([self.forum_search_num, self.change_type, self.changed_field, self.new_value, self.change_id,
                    self.name, self.link,
                    self.status, self.n_of_replies, self.title, self.age, self.age_wording, self.forum_folder,
                    self.search_latitude, self.search_longitude, self.activities, self.comments, self.comments_inforg,
                    self.message, self.processed, self.managers, self.start_time, self.ignore, self.region])


class User:
    def __init__(self,
                 user_id=None,
                 username_telegram=None,
                 notification_preferences=None,
                 user_latitude=None,
                 user_longitude=None,
                 user_regions=None,
                 user_in_multi_regions=True,
                 user_corr_regions=None,
                 user_new_search_notifs=None
                 ):
        self.user_id = user_id
        self.username_telegram = username_telegram
        self.notification_preferences = notification_preferences
        self.user_latitude = user_latitude
        self.user_longitude = user_longitude
        self.user_regions = user_regions
        self.user_in_multi_regions = user_in_multi_regions
        self.user_corr_regions = user_corr_regions
        self.user_new_search_notifs = user_new_search_notifs

    def __str__(self):
        return str([self.user_id, self.username_telegram, self.notification_preferences, self.user_latitude,
                    self.user_longitude, self.user_regions, self.user_in_multi_regions, self.user_corr_regions,
                    self.user_new_search_notifs])


def get_config_info(event):
    """get the canary deployment config"""

    config = {'use_canary': False}
    try:
        message_from_pubsub = process_pubsub_message(event)
        config = ast.literal_eval(message_from_pubsub)

        logging.info('config received: ' + str(config))
    except Exception as e:
        logging.error('config was not received via pub/sub:' + repr(e))
        logging.exception(e)

    return config


def compose_new_records_from_change_log(conn, is_prod):
    """compose the New Records list of the unique New Records in Change Log: one Record = One line in Change Log"""

    global new_records_list

    if is_prod:
        delta_in_cl = conn.execute(
            """SELECT search_forum_num, changed_field, new_value, id, change_type FROM change_log 
            WHERE notification_sent is NULL 
            OR notification_sent='s' ORDER BY id LIMIT 1; """
        ).fetchall()
    else:
        delta_in_cl = conn.execute(
            """SELECT search_forum_num, changed_field, new_value, id, change_type FROM change_log 
            WHERE notification_sent is NULL 
            AND notif_sent_staging is NULL ORDER BY id DESC; """
        ).fetchall()

    for i in range(len(delta_in_cl)):
        one_line_in_change_log = list(delta_in_cl[i])
        new_line = LineInChangeLog()
        new_line.forum_search_num = one_line_in_change_log[0]
        new_line.changed_field = one_line_in_change_log[1]
        new_line.new_value = one_line_in_change_log[2]
        new_line.change_id = one_line_in_change_log[3]
        new_line.change_type = one_line_in_change_log[4]

        # Convert preference from Change_Log Naming into User_Preferences Naming
        dictionary = {'new_search': 'new_searches', 'status_change': 'status_changes',
                      'replies_num_change': 'comments_changes', 'title_change': 'title_changes',
                      'inforg_replies': 'inforg_comments'}
        new_line.changed_field_for_user = dictionary[new_line.changed_field]

        try:
            # define if this Record in change log is about New comments and New comments were already loaded into msgs
            decision = 'add'

            if len(new_records_list) > 0 and new_line.changed_field == 'replies_num_change':
                for j in new_records_list:
                    if j.forum_search_num == new_line.forum_search_num and j.changed_field == new_line.changed_field:
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
    """add the add'l data from Searches into New Records list"""

    global new_records_list

    try:

        # TODO: in the future there's a need to limit the number of searches in this query (limit by time?)
        # TODO: MEMO: as of Jan 2022 - there are 5000 lines – not crucially much
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

                    # case: when new search's status is already not "Ищем" – to be ignored
                    if r_line.status != 'Ищем' and r_line.changed_field == "new_search":
                        r_line.ignore = 'y'
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
            comments = conn.execute("""SELECT comment_url, comment_text, comment_author_nickname, comment_author_link, 
            search_forum_num, comment_num FROM comments WHERE notification_sent IS NULL;""").fetchall()

        elif type_of_comments == 'inforg':
            comments = conn.execute("""SELECT comment_url, comment_text, comment_author_nickname, comment_author_link, 
                        search_forum_num, comment_num FROM comments WHERE notification_sent IS NULL 
                        AND LOWER(LEFT(comment_author_nickname,6))='инфорг';""").fetchall()
        else:
            comments = None

        # look for matching Forum Search Num    bers in New Records List & Comments
        for r_line in new_records_list:
            if r_line.changed_field in {'replies_num_change', 'inforg_replies'}:
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
    msg += ' – обновление заголовка поиска по'
    msg += ' <a href="' + link + '">'
    msg += name
    if name[0].isupper() and age and age != 0:
        msg += ' '
        msg += age_wording
    msg += '</a>\n'

    return msg


def add_tel_link(incoming_text, modifier='all'):
    """check is text contains phone number and replaces it with clickable version, also removes [tel] tags"""

    outcome_text = None

    # Modifier for all users
    if modifier == 'all':
        outcome_text = incoming_text
        nums = re.findall(r"(?:\+7|7|8)[\s]?[\s\-(]?[\s]?[\d]{3}[\s\-)]?[\s]?[\d]{3}[\s\-]?[\d]{2}[\s\-]?[\d]{2}",
                          incoming_text)
        for num in nums:
            outcome_text = outcome_text.replace(num, '<code>' + str(num) + '</code>')

        phpbb_tags_to_delete = {'[tel]', '[/tel]'}
        for tag in phpbb_tags_to_delete:
            outcome_text = outcome_text.replace(tag, '', 5)

    # Modifier for Admin
    else:
        pass

    return outcome_text


def enrich_new_records_with_message_texts():
    """add user-independent message texts to New Records list"""

    global new_records_list

    last_line = None

    try:
        for line in new_records_list:
            last_line = line
            if line.changed_field == 'new_search':
                # TODO: temporary TRY if everything under try works - than Try/except is not needed.
                #  Except keeps the "old" approach
                try:
                    start = line.start_time
                    now = datetime.datetime.now()
                    days_since_search_start = (now - start).days
                    # if "old" search - no need to compose & send message
                    if days_since_search_start < 2:
                        line.message = compose_com_msg_on_new_search(line.link, line.name, line.age, line.age_wording,
                                                                     line.activities, line.managers)
                    else:
                        line.ignore = 'y'
                except Exception as e4:
                    logging.error('DBG.N.108.EXC:' + repr(e4))
                    logging.exception(e4)
                    notify_admin('[comp_notif]: ERROR in try in enrich_new_records_with_mess_txts')
                    line.message = compose_com_msg_on_new_search(line.link, line.name, line.age, line.age_wording,
                                                                 line.activities, line.managers)

            elif line.changed_field == 'status_change':
                line.message = compose_com_msg_on_status_change(line.status, line.link, line.name, line.age,
                                                                line.age_wording, line.region)
            elif line.changed_field == 'title_change':
                line.message = compose_com_msg_on_title_change(line.title, line.link, line.name, line.age,
                                                               line.age_wording)
            elif line.changed_field == 'replies_num_change':
                line.message = compose_com_msg_on_new_comments(line.link, line.name, line.age, line.age_wording,
                                                               line.comments)
            elif line.changed_field == 'inforg_replies':
                line.message = compose_com_msg_on_inforg_comments(line.link, line.name, line.age, line.age_wording,
                                                                  line.comments_inforg, line.region)

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
            (SELECT u.user_id, u.username_telegram, uc.latitude, uc.longitude FROM users as u 
            LEFT JOIN 
            user_coordinates as uc ON u.user_id=uc.user_id 
            WHERE u.status = 'unblocked' or u.status is Null) ns 
            LEFT JOIN 
            user_stat st ON ns.user_id=st.user_id;"""
        ).fetchall()

        for line in users:
            new_line = User()
            new_line.user_id = line[0]
            new_line.username_telegram = line[1]
            new_line.user_latitude = line[2]
            new_line.user_longitude = line[3]
            if line[4] == 'None' or line[4] is None:
                new_line.user_new_search_notifs = 0
            else:
                new_line.user_new_search_notifs = int(line[4])
            users_list.append(new_line)

        logging.info('User List composed')
        # logging.info('User List: ' + str(users_list))

    except Exception as e:
        logging.error('Not able to compose Users List: ' + repr(e))
        logging.exception(e)

    return None


def enrich_users_list_with_notification_preferences(conn):
    """add the add'l data on notification preferences from User_preferences into Users List"""

    global users_list

    try:
        notif_prefs = conn.execute(
            """SELECT user_id, preference FROM user_preferences;"""
        ).fetchall()

        # look for matching User_ID in Users List & Notification Preferences
        for u_line in users_list:
            prefs_array = []
            for np_line in notif_prefs:
                # when match is found
                if u_line.user_id == np_line[0]:
                    prefs_array.append(np_line[1])
            u_line.notification_preferences = prefs_array

        logging.info('Users List enriched with Notification Prefs')

    except Exception as e:
        logging.error('Not able to enrich Users List with Notification Prefs: ' + str(e))
        logging.exception(e)

    return None


def enrich_users_list_with_user_regions(conn):
    """add the add'l data on user preferred regions from User Regional Preferences into Users List"""

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
        logging.error('Not able to get the lists of Admins & Testers: ' + repr(e))
        logging.exception(e)

    return list_of_admins, list_of_testers


def enrich_users_by_corrected_regions(conn, is_prod, stage_share):
    """divide the list of users by prod & stage (by forum folder)"""

    global users_list

    try:

        share = stage_share / 100

        # Extract the latest user base and combine: by forum folder, number of users in total, for stage and for prod,
        # all excluding Admins & Testers
        sql_text = sqlalchemy.text("""select s2.forum_folder_num, s2.ttl_users, ROUND(s2.ttl_users*:a) stage_users, 
            (s2.ttl_users-ROUND(s2.ttl_users*:a)) prod_users from (select urp.forum_folder_num, 
            count(urp.user_id) ttl_users from (select u.user_id, u.status, ur.role from users u 
            LEFT JOIN user_roles ur ON u.user_id = ur.user_id WHERE ur.role is NULL 
            and (u.status = 'unblocked' or u.status is NULL)) s LEFT JOIN user_regional_preferences urp 
            ON s.user_id=urp.user_id GROUP BY urp.forum_folder_num order by ttl_users desc) s2;""")
        folder_user_volume_split = conn.execute(sql_text, a=share).fetchall()

        # extract the folder_number to user_id list
        folder_user_list = conn.execute("""select urp.forum_folder_num, urp.user_id from 
            (select u.user_id, u.status, ur.role from users u LEFT JOIN user_roles ur ON u.user_id = ur.user_id 
            WHERE ur.role is NULL and (u.status = 'unblocked' or u.status is NULL)) s 
            LEFT JOIN user_regional_preferences urp ON s.user_id=urp.user_id 
            ORDER BY forum_folder_num, user_id;""").fetchall()

        # combine the list of folders
        folder_list = []
        for line in folder_user_list:
            if line[0] in folder_list:
                pass
            else:
                folder_list.append(line[0])

        # compose the final folder & user matrix
        final_users_split = []
        for folder in folder_list:

            staging_users_volume = 0
            for line in folder_user_volume_split:
                if line[0] == folder:
                    staging_users_volume = line[2]

            i = 0
            for line in folder_user_list:

                if folder == line[0]:
                    if i < staging_users_volume:
                        final_users_split.append([line[0], line[1], 'stag'])
                        i += 1
                    else:
                        final_users_split.append([line[0], line[1], 'prod'])
                        i += 1
                else:
                    pass

        for user in users_list:
            user_corr_folders = []
            for line in final_users_split:
                if user.user_id == line[1]:
                    if (is_prod and line[2] == 'prod') or (not is_prod and line[2] == 'stag'):
                        user_corr_folders.append(line[0])
            user.user_corr_regions = user_corr_folders

        logging.info('Users enriched with Regions corrected to Canary')

    except Exception as e:
        logging.error('Not able to enrich Users with Regions corrected to Canary: ' + repr(e))
        logging.exception(e)

    return None


def enrich_users_with_admins_and_testers(is_prod, config, list_of_admins, list_of_testers):
    """add info if admins and testers"""

    global users_list

    try:
        for line in list_of_admins:
            for user in users_list:
                if str(user.user_id) == str(line):
                    adm_prod = config['canary_params']['admin_on_prod']
                    adm_stag = config['canary_params']['admin_on_stage']
                    if (adm_prod and is_prod) or (adm_stag and not is_prod):
                        user.user_corr_regions = user.user_regions
                    else:
                        user.user_corr_regions = []
                    pass

        for line in list_of_testers:
            for user in users_list:
                if str(user.user_id) == str(line):
                    adm_prod = config['canary_params']['testers_on_prod']
                    adm_stag = config['canary_params']['testers_on_stage']
                    if (adm_prod and is_prod) or (adm_stag and not is_prod):
                        user.user_corr_regions = user.user_regions
                    else:
                        user.user_corr_regions = []
                    pass

        logging.info('Users enriched with Admins & Testers')

    except Exception as e:
        logging.error('Not able to enrich Users with Admins & Testers: ' + repr(e))
        logging.exception(e)

    return None


def mark_new_records_as_being_processed(conn, is_prod):
    """Mark all new records as ones being processed right now"""

    if is_prod:
        for record in new_records_list:
            sql_text = sqlalchemy.text("""UPDATE change_log SET notification_sent = 's' WHERE id=:a;""")
            conn.execute(sql_text, a=record.change_id)

    logging.info('New Records marked as being processed')

    return None


def mark_new_comments_as_being_processed(conn, is_prod):
    """marks all the new comments in SQL as processed, to avoid processing in the next iteration"""

    for record in new_records_list:
        if record.changed_field == 'replies_num_change' and record.ignore != 'y':
            if is_prod:
                sql_text = sqlalchemy.text("UPDATE comments SET notification_sent = 's' WHERE search_forum_num=:a;")
            else:
                sql_text = sqlalchemy.text("UPDATE comments SET notif_sent_staging = 's' WHERE search_forum_num=:a;")
            conn.execute(sql_text, a=record.forum_search_num)

    logging.info('New Comments marked as being processed')

    return None


def log_debug_message(admin_user_id):
    """only for debug purposes"""

    logging.info('new_records_list after enrichment: ')
    for line in new_records_list:
        logging.info('new_rec: ' + str(line))

    logging.info('Admin User after enrichment: ')
    for line in users_list:
        if str(line.user_id) == str(admin_user_id):
            logging.info('Admin: ' + str(line))

    # logging.info('Users List after enrichment: ')
    # for line in users_list:
    #    logging.info(str(line))

    return None


def record_notification_statistics(conn):
    """records +1 into users' statistics of new searches notification"""

    global stat_list_of_recipients

    logging.info('--->WE ARE HERE0: ' + str(stat_list_of_recipients))
    dict_of_user_and_number_of_new_notifs = {i: stat_list_of_recipients.count(i) for i in stat_list_of_recipients}

    logging.info('--->WE ARE HERE1: ' + str(dict_of_user_and_number_of_new_notifs))

    try:
        for user_id in dict_of_user_and_number_of_new_notifs:
            number_to_add = dict_of_user_and_number_of_new_notifs[user_id]

            logging.info('--->WE ARE HERE2: ' + str(number_to_add))

            sql_text = sqlalchemy.text("""
            INSERT INTO user_stat (user_id, num_of_new_search_notifs) 
            VALUES(:a, :b)
            ON CONFLICT (user_id) DO 
            UPDATE SET num_of_new_search_notifs = :b + 
            (SELECT num_of_new_search_notifs from user_stat WHERE user_id = :a) 
            WHERE user_stat.user_id = :a;
            """)
            conn.execute(sql_text, a=int(user_id), b=int(number_to_add))

            logging.info('--->WE ARE HERE3: ' + str(sql_text))

    except Exception as e:
        logging.error('Recording statistics in notification script failed' + repr(e))
        logging.exception(e)

    return None


def iterate_over_all_users_and_updates(bot_2, is_prod, using_canary, conn):
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
                                change_log_id) 
                            VALUES (:a, :b, :c, :d, :e, :f, :g, :h)
                            RETURNING message_id;
                            """)

        raw_data_ = conn.execute(sql_text_,
                                 a=mailing_id_,
                                 b=user_id_,
                                 c=message_,
                                 d=message_without_html_,
                                 e=message_type_,
                                 f=message_params_,
                                 g=message_group_id_,
                                 h=change_log_id_
                                 ).fetchone()

        return raw_data_[0]

    def get_from_sql_if_was_notified_already(mailing_id_, user_id_, message_type_):
        """check in sql if this user was already notified re this change_log record"""

        sql_text_ = sqlalchemy.text("""
        SELECT EXISTS (
            SELECT s2.*, s3.source_script from (
                SELECT s1.*, nbu.mailing_id, nbu.user_id, nbu.message_type 
                FROM (
                    SELECT message_id from notif_by_user_status 
                    WHERE event = 'completed'
                ) as s1 
                LEFT JOIN notif_by_user nbu 
                ON s1.message_id=nbu.message_id
                ) as s2 
                INNER JOIN (
                    SELECT mailing_id, source_script 
                    FROM notif_mailings 
                    WHERE change_log_id = (
                        SELECT change_log_id from notif_mailings 
                        WHERE mailing_id=:a
                    )
                ) as s3 
                ON s2.mailing_id=s3.mailing_id 
                WHERE s2.user_id=:b AND s2.message_type=:c
        );""")

        user_was_already_notified = conn.execute(sql_text_,
                                                 a=mailing_id_,
                                                 b=user_id_,
                                                 c=message_type_
                                                 ).fetchone()[0]

        return user_was_already_notified

    def get_from_sql_list_of_already_notified_users(mailing_id_):
        """check in sql if this user was already notified re this change_log record"""

        sql_text_ = sqlalchemy.text("""
        SELECT s2.*, s3.source_script from (
                SELECT s1.*, nbu.mailing_id, nbu.user_id, nbu.message_type 
                FROM (
                    SELECT message_id from notif_by_user_status 
                    WHERE event = 'completed'
                ) as s1 
                LEFT JOIN notif_by_user nbu 
                ON s1.message_id=nbu.message_id
                ) as s2 
                INNER JOIN (
                    SELECT mailing_id, source_script 
                    FROM notif_mailings 
                    WHERE change_log_id = (
                        SELECT change_log_id from notif_mailings 
                        WHERE mailing_id=:a
                    )
                ) as s3 
                ON s2.mailing_id=s3.mailing_id
        ;""")

        raw_data_ = conn.execute(sql_text_, a=mailing_id_).fetchall()

        users_who_was_notified = []
        # TODO: in the future it's needed to be assumed re text - non text and delete duplicated users here
        logging.info("raw_data_:")
        logging.info(raw_data_)
        for line in raw_data_:
            users_who_was_notified.append(line[2])

        return users_who_was_notified

    def get_the_new_group_id():
        """define the max message_group_id in notif_by_user and add +1"""

        raw_data_ = conn.execute("""SELECT MAX(message_group_id) FROM notif_by_user;""").fetchone()

        if raw_data_[0]:
            next_id = raw_data_[0] + 1
        else:
            next_id = 0

        return next_id

    global new_records_list
    global users_list
    global coordinates_format
    global stat_list_of_recipients

    global srch_id
    global chng_id
    global chng_type
    global mailing_id

    stat_list_of_recipients = []  # still not clear why w/o it – saves data from prev iterations
    number_of_situations_checked = 0
    number_of_messages_sent = 0
    cleaner = re.compile('<.*?>')

    logging.info('---> PRE-INFO1: ' + str(stat_list_of_recipients))

    # TODO: DEBUG - FOR EXCLUSION OF ADMIN AS A TEST
    list_of_admins_2, list_of_testers_2 = get_list_of_admins_and_testers(conn)

    # TODO: added testers
    list_of_admins_2 = list_of_admins_2 + list_of_testers_2

    try:

        # execute new updates one-by-one
        for new_record in new_records_list:

            # skip ignored lines which don't require a notification
            if new_record.ignore != 'y':

                s_lat = new_record.search_latitude
                s_lon = new_record.search_longitude
                changed_field = new_record.changed_field

                mailing_type_id = 99  # which is for 'non defined'
                if changed_field == 'new_search':
                    mailing_type_id = 0
                elif changed_field == 'status_change':
                    mailing_type_id = 1
                elif changed_field == 'inforg_replies':
                    mailing_type_id = 4
                elif changed_field == 'title_change':
                    mailing_type_id = 2
                elif changed_field == 'replies_num_change':
                    mailing_type_id = 3

                # check if this change_log record was somehow processed
                sql_text = sqlalchemy.text("""
                                    SELECT EXISTS (SELECT * FROM notif_mailings WHERE change_log_id=:a);
                                    """)
                this_record_was_processed_already = conn.execute(sql_text, a=new_record.change_id).fetchone()[0]

                # TODO: DEBUG
                if this_record_was_processed_already:
                    logging.info('[comp_notif]: 2 MAILINGS for 1 CHANGE LOG RECORD identified')

                # record into SQL table notif_mailings
                sql_text = sqlalchemy.text("""
                INSERT INTO notif_mailings (topic_id, source_script, mailing_type, change_log_id) 
                VALUES (:a, :b, :c, :d)
                RETURNING mailing_id;
                """)
                raw_data = conn.execute(sql_text,
                                        a=new_record.forum_search_num,
                                        b='notifications_script',
                                        c=mailing_type_id,
                                        d=new_record.change_id
                                        ).fetchone()

                srch_id = new_record.forum_search_num
                mailing_id = raw_data[0]
                chng_type = mailing_type_id
                chng_id = new_record.change_id

                logging.info(mailing_id)

                users_who_should_not_be_informed = get_from_sql_list_of_already_notified_users(mailing_id)
                logging.info('users_who_should_not_be_informed:')
                logging.info(users_who_should_not_be_informed)
                logging.info('in total ' + str(len(users_who_should_not_be_informed)))

                # record into SQL table notif_mailings_status
                sql_text = sqlalchemy.text("""
                                    INSERT INTO notif_mailing_status (mailing_id, event, event_timestamp) 
                                    VALUES (:a, :b, :c);
                                    """)
                conn.execute(sql_text,
                             a=mailing_id,
                             b='created',
                             c=datetime.datetime.now())

                # then go to user-level
                for user in users_list:

                    logging.info('test here 1')
                    if user.user_id not in users_who_should_not_be_informed:

                        logging.info('test here 2')
                        u_lat = user.user_latitude
                        u_lon = user.user_longitude
                        user_notif_prefs = user.notification_preferences

                        if using_canary:
                            user_reg_prefs = user.user_corr_regions
                        else:
                            user_reg_prefs = user.user_regions

                        # as user can have multi-reg preferences – check every region
                        for region in user_reg_prefs:

                            if str(region) == str(new_record.forum_folder):

                                region_to_show = None
                                if user.user_in_multi_regions:
                                    region_to_show = new_record.region

                                # as user can have several notification preferences – check every preference
                                for notif_pref in user_notif_prefs:

                                    # check if user wants to receive this kind of notifications
                                    if notif_pref == new_record.changed_field_for_user or notif_pref == 'all':

                                        # on this step - we're certain: user should receive the notification
                                        # start preparation on notifications
                                        message = ''
                                        number_of_situations_checked += 1

                                        if changed_field == 'new_search':
                                            sent_already = user.user_new_search_notifs
                                            message = compose_individual_message_on_new_search(new_record, s_lat, s_lon,
                                                                                               u_lat, u_lon,
                                                                                               region_to_show,
                                                                                               sent_already)

                                        elif changed_field == 'status_change':
                                            message = new_record.message[0]
                                            if user.user_in_multi_regions and new_record.message[1]:
                                                message += new_record.message[1]

                                        elif changed_field == 'inforg_replies':
                                            message = new_record.message[0]
                                            if user.user_in_multi_regions and new_record.message[1]:
                                                message += new_record.message[1]
                                            if new_record.message[2]:
                                                message += new_record.message[2]

                                        elif changed_field == 'replies_num_change':
                                            message = new_record.message[0]

                                        elif changed_field == 'title_change':
                                            message = new_record.message

                                        if message:

                                            logging.info('test here 3')
                                            if changed_field in {'new_search'}:
                                                message_group_id = get_the_new_group_id()
                                            else:
                                                message_group_id = None
                                            logging.info('test here 4')

                                            message_type = 'text'
                                            no_preview = True
                                            this_user_was_notified = False

                                            logging.info('test here 5')
                                            if this_record_was_processed_already:
                                                this_user_was_notified = get_from_sql_if_was_notified_already(
                                                    mailing_id, user.user_id, message_type)
                                                logging.info('this user was notified already {}, {}'.format(
                                                    user.user_id, this_user_was_notified))
                                                if user.user_id in users_who_should_not_be_informed:
                                                    logging.info('this user is in the list of non-notifiers')
                                                else:
                                                    logging.info('this user is NOT in the list of non-notifiers')

                                            logging.info('test here 6')
                                            if not this_user_was_notified:

                                                logging.info('test here 7')
                                                # record into SQL table notif_by_user
                                                # TODO: make text more compact within 50 symbols
                                                message_without_html = re.sub(cleaner, '', message)

                                                message_params = {'parse_mode': 'HTML',
                                                                  'disable_web_page_preview': 'no_preview'}
                                                message_id = save_to_sql_notif_by_user(mailing_id, user.user_id,
                                                                                       message,
                                                                                       message_without_html,
                                                                                       message_type,
                                                                                       message_params, message_group_id,
                                                                                       chng_id)

                                                logging.info('test here 8')
                                                send_single_message(bot_2, user.user_id, message,
                                                                    no_preview, 'message', None,
                                                                    None, user, new_record, message_id, conn,
                                                                    mailing_id, chng_id, list_of_admins_2, chng_type)

                                                # TODO: testing notif_mailings

                                                if changed_field == 'new_search':
                                                    stat_list_of_recipients.append(user.user_id)

                                                if changed_field == 'new_search' and s_lat and s_lon:
                                                    message_params = {'latitude': s_lat,
                                                                      'longitude': s_lon}

                                                    message_id = save_to_sql_notif_by_user(mailing_id, user.user_id,
                                                                                           None,
                                                                                           None, 'coords',
                                                                                           message_params,
                                                                                           message_group_id,
                                                                                           chng_id)

                                                    send_single_message(bot_2, user.user_id,
                                                                        None, None, 'location', s_lat,
                                                                        s_lon, user, new_record,
                                                                        message_id, conn, mailing_id, chng_id,
                                                                        list_of_admins_2, chng_type)

                                                number_of_messages_sent += 1

                # mark this line as all-processed
                new_record.processed = 'yes'
                logging.info('test here 9')

            # mark all ignored lines as processed
            else:
                new_record.processed = 'yes'

        """DEBUG"""
        prefix = ''
        if not is_prod:
            prefix = 'Staging Script:\n'
        n1 = 'ttl sent = ' + str(number_of_messages_sent)
        n2 = 'checked  = ' + str(number_of_situations_checked)
        notify_admin(prefix + n1 + '\n' + n2)
        """DEBUG"""

        logging.info(prefix + n1 + '\n' + n2)
        logging.info('Iterations over all Users and Updates are done')

    except Exception as e1:
        logging.error('Not able to Iterate over all Users and Updates: ' + repr(e1))
        logging.exception(e1)

    logging.info('---> PRE-INFO2: ' + str(stat_list_of_recipients))

    return None


def generate_yandex_maps_place_link2(lat, lon, param):
    """generate a link to yandex map with lat/lon"""

    global coordinates_format

    if param == 'map':
        display = 'Карта'
    else:
        display = param

    msg = '<a href="https://yandex.ru/maps/?pt='
    msg += str(lon) + ',' + str(lat)
    msg += '&z=11&l=map">' + display + '</a>'

    return msg


def write_message_sending_status(conn_, message_id_, result, mailing_id_, change_log_id_, user_id_, message_type_):
    """write to SQL table notif_by_user_status the status of individual message sent"""

    try:
        # record into SQL table notif_by_user_status
        sql_text = sqlalchemy.text("""
                    INSERT INTO notif_by_user_status (
                        message_id, 
                        event, 
                        event_timestamp,
                        mailing_id,
                        change_log_id,
                        user_id,
                        message_type,
                        context) 
                    VALUES (:a, :b, :c, :d, :e, :f, :g, :h);
                    """)

        if result in {'created', 'completed'}:
            conn_.execute(sql_text,
                          a=message_id_,
                          b=result,
                          c=datetime.datetime.now(),
                          d=mailing_id_,
                          e=change_log_id_,
                          f=user_id_,
                          g=message_type_,
                          h='comp_notifs'
                          )
        else:
            # TODO: debug notify
            notify_admin('[comp_notifs]: message {}, sending status is {} for conn'.format(message_id_, result))
            with sql_connect().connect() as conn2:

                conn2.execute(sql_text,
                              a=message_id_,
                              b=result,
                              c=datetime.datetime.now(),
                              d=mailing_id_,
                              e=change_log_id_,
                              f=user_id_,
                              g=message_type_,
                              h='comp_notifs'
                              )
            # TODO: debug notify
            notify_admin('[comp_notifs]]: message {}, sending status is {} for conn2'.format(message_id_, result))

    except:  # noqa
        notify_admin('ERR mink write to SQL notif_by_user_status, message_id {}, status {}'.format(message_id_, result))

    return None


def send_single_message(bot_2, user_id, message, no_preview, mes_type, lat, lon, user, new_record, message_id, conn,
                        mailing_id_, change_log_id, list_of_admins_, change_type_):
    """send individual notification message"""

    global analytics_notif_times
    if mes_type == 'message':
        message_type = 'text'
    else:
        message_type = 'coords'

    analytics_sm_start = datetime.datetime.now()

    write_message_sending_status(conn, message_id, 'created', mailing_id_, change_log_id, user_id, message_type)

    try:

        admin_debug_trigger = (user_id in list_of_admins_) or user_id <= 367905643
        if mes_type == 'message':

            # TODO: temp limitation
            if not admin_debug_trigger:
                bot_2.sendMessage(chat_id=user_id, text=message, parse_mode='HTML', disable_web_page_preview=no_preview)

            """DEBUG"""
            logging.info('------msg to user - BEGINNING ------')
            logging.info(user)
            logging.info(new_record)
            logging.info(new_record.message)
            logging.info(user.user_corr_regions)
            logging.info('------msg to user - END ------')
            """DEBUG"""

        elif mes_type == 'location':
            # TODO: temp limitation
            if not admin_debug_trigger:
                bot_2.sendLocation(chat_id=user_id, latitude=lat, longitude=lon)

        # TODO: temp limitation
        if not admin_debug_trigger:
            write_message_sending_status(conn, message_id, 'completed', mailing_id_, change_log_id, user_id,
                                         message_type)

    except Exception as e:

        error_description = str(e)

        # if user blocked the bot OR user is deactivated (deleted telegram account)
        if error_description.find('bot was blocked by the user') != -1 \
                or error_description.find('user is deactivated') != -1:
            if error_description.find('bot was blocked by the user') != -1:
                action = 'block_user'
            else:
                action = 'delete_user'
            message_for_pubsub = {'action': action, 'info': {'user': user_id}}
            publish_to_pubsub('topic_for_user_management', message_for_pubsub)

            logging.info('Identified user id={} to do {}'.format(user_id, action))

            write_message_sending_status(conn, message_id, 'cancelled', mailing_id_, change_log_id, user_id,
                                         message_type)

        # if too many requests to Telegram – notify admin on it
        elif error_description.find('429') != -1:
            logging.error('Not able to send to Telegram (429): ' + error_description)
            logging.exception(e)

            write_message_sending_status(conn, message_id, 'failed', mailing_id_, change_log_id, user_id, message_type)

        # if issue with connection to SQL
        elif error_description.find('Connection reset by peer') != -1:
            logging.error('Connection reset by peer (104): ' + error_description)
            logging.exception(e)

            time.sleep(1)
            write_message_sending_status(conn, message_id, 'failed', mailing_id_, change_log_id, user_id, message_type)

        else:
            logging.error('Not able to send {} ({}) to user {}: {}'.format(mes_type, str(message),
                                                                           user_id, error_description))
            logging.exception(e)

            time.sleep(5)
            write_message_sending_status(conn, message_id, 'failed', mailing_id_, change_log_id, user_id, message_type)

    analytics_sm_finish = datetime.datetime.now()
    analytics_sm_duration = (analytics_sm_finish - analytics_sm_start).total_seconds()
    analytics_notif_times.append(analytics_sm_duration)

    return None


def compose_individual_message_on_new_search(new_record, s_lat, s_lon, u_lat, u_lon, region_to_show, num_of_sent):
    """compose individual message for notification of every user on new search"""

    # 0. Heading and Region clause if user is 'multi-regional'
    message = 'Новый поиск'
    if region_to_show:
        message += ' в регионе ' + str(region_to_show) + '!\n'
    else:
        message += '! \n'

    # 1. Search important attributes - common part (e.g. 'Внимание, выезд!)
    if new_record.message[1]:
        message += new_record.message[1]

    # 2. Person (e.g. 'Иванов 60' )
    message += '\n' + new_record.message[0]

    # 3. Dist & Dir – individual part for every user
    if s_lat and s_lon and u_lat and u_lon:
        try:
            dist, direc = define_dist_and_dir_to_search(s_lat, s_lon, u_lat, u_lon)
            direction = '\n\nОт вас ~' + str(dist) + ' км ' + direc

            message += generate_yandex_maps_place_link2(s_lat, s_lon, direction)
            message += '\n'
            message += '<code>' + str(coordinates_format.format(float(s_lat)))
            message += ', ' + str(coordinates_format.format(float(s_lon)))
            message += '</code>'

        except Exception as ee:
            logging.error('Not able to compose individual msg with distance & direction, params: '
                          + str([new_record, s_lat, s_lon, u_lat, u_lon]) + ', error: ' + repr(ee))
            logging.exception(ee)

    if s_lat and s_lon and not u_lat and not u_lon:
        try:
            message += '\n\n' + generate_yandex_maps_place_link2(s_lat, s_lon, 'map')

        except Exception as ee:
            logging.error('Not able to compose message with Yandex Map Link, params:'
                          + str([new_record, s_lat, s_lon, u_lat, u_lon]) + ', error:' + repr(ee))
            logging.exception(ee)

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


def publish_to_pubsub(topic_name, message):
    """publish a new message to pub/sub"""

    global project_id

    topic_path = publisher.topic_path(project_id, topic_name)
    message_json = json.dumps({'data': {'message': message}, })
    message_bytes = message_json.encode('utf-8')

    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publish succeeded
        logging.info('Sent pub/sub message: ' + str(message))

    except Exception as e:
        logging.error('Not able to send pub/sub message: ' + repr(e))
        logging.exception(e)

    return None


def notify_admin(message):
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub('topic_notify_admin', message)

    return None


def mark_new_records_as_processed(conn, is_prod):
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
            if is_prod:
                sql_text = sqlalchemy.text("""UPDATE change_log SET notification_sent = 'y' WHERE id=:a;""")

            else:
                sql_text = sqlalchemy.text("""UPDATE change_log SET notif_sent_staging = 'y' WHERE id=:a;""")
            conn.execute(sql_text, a=record)

        for record in change_id_list_ignored:
            if is_prod:
                sql_text = sqlalchemy.text("""UPDATE change_log SET notification_sent = 'n' WHERE id=:a;""")
            else:
                sql_text = sqlalchemy.text("""UPDATE change_log SET notif_sent_staging = 'n' WHERE id=:a;""")
            conn.execute(sql_text, a=record)

        logging.info('The list of Updates that are processed and not ignored: ' + str(change_id_list))
        logging.info('The list of Updates that are processed and ignored: ' + str(change_id_list_ignored))
        logging.info('All Updates are marked as processed in Change Log')

    except Exception as e:

        # For Safety Sake – Update Change_log SQL table, setting 'y' everywhere
        if is_prod:
            conn.execute(
                """UPDATE change_log SET notification_sent = 'y' WHERE notification_sent is NULL 
                OR notification_sent='s';"""
            )
        else:
            conn.execute(
                """UPDATE change_log SET notif_sent_staging = 'y' WHERE notification_sent is NULL;"""
            )

        logging.error('Not able to mark Updates as Processed in Change Log: ' + repr(e))
        logging.exception(e)
        logging.info('Due to error, all Updates are marked as processed in Change Log')
        notify_admin('ERROR: Not able to mark Updates as Processed in Change Log!')

    return None


def mark_new_comments_as_processed(conn, is_prod):
    """mark in SQL table Comments all the comments that were proceed at this step, basing on search_forum_id"""

    try:
        change_id_list = []
        for record in new_records_list:
            if record.processed == 'yes' and record.changed_field == 'replies_num_change' and record.ignore != 'y':
                change_id_list.append(record.forum_search_num)

        for record in change_id_list:
            if is_prod:
                sql_text = sqlalchemy.text("UPDATE comments SET notification_sent = 'y' WHERE search_forum_num=:a;")
            else:
                sql_text = sqlalchemy.text("UPDATE comments SET notif_sent_staging = 'y' WHERE search_forum_num=:a;")
            conn.execute(sql_text, a=record)

        logging.info('The list of Updates with Comments that are processed and not ignored: ' + str(change_id_list))
        logging.info('All Comments are marked as processed')

    except Exception as e:

        if is_prod:
            sql_text = sqlalchemy.text("""UPDATE comments SET notification_sent = 'y' WHERE notification_sent is Null 
                                        OR notification_sent = 's';""")
        else:
            sql_text = sqlalchemy.text("""UPDATE comments SET notif_sent_staging = 'y' WHERE notification_sent is Null 
                                        OR notification_sent = 's';""")
        conn.execute(sql_text)

        logging.error('Not able to mark Comments as Processed: ' + repr(e))
        logging.exception(e)
        logging.info('Due to error, all Comments are marked as processed')
        notify_admin('ERROR: Not able to mark Comments as Processed!')

    return None


def pubsub_notification_trigger(event, context):  # noqa
    """key function which is initiated by Pub/Sub"""

    global new_records_list
    global users_list
    global db
    global analytics_notif_times
    global script_start_time

    script_start_time = datetime.datetime.now()

    # TODO: to delete everything connected to config / canary etc.
    # Get config of Canary Deployment, which is needed only for Development phase
    # config = get_config_info(event)
    # using_canary = config['use_canary']
    # is_prod = (gcp_function_name == 'prod_notification_script')
    using_canary = False
    is_prod = True

    if is_prod or (not is_prod and using_canary):

        # TODO: should be avoided in the future (doesn't return None help?)
        # the below two lines are required - in other case these arrays are not always empty,
        # spent 2 hours - don't know why using '=[]' in the body of this Script (lines ~14-15) is not sufficient
        new_records_list = []
        users_list = []

        # initiate SQL connection
        db = sql_connect()
        conn = db.connect()

        # initiate Prod Bot
        bot_token = get_secrets("bot_api_token__prod")
        bot_2 = Bot(token=bot_token)

        # TODO - do we need it still - or to take it from PSQL?
        admin_user_id = get_secrets("my_telegram_id")

        # compose New Records List: the delta from Change log
        compose_new_records_from_change_log(conn, is_prod)

        # only if there are updates in Change Log
        if new_records_list:

            # enrich New Records List with all the updates that should be in notifications
            enrich_new_records_from_searches(conn)
            enrich_new_records_with_search_activities(conn)
            enrich_new_records_with_managers(conn)
            enrich_new_records_with_comments(conn, 'all')
            enrich_new_records_with_comments(conn, 'inforg')
            enrich_new_records_with_message_texts()

            # compose Users List: all the notifications recipients' details
            compose_users_list_from_users(conn)
            enrich_users_list_with_notification_preferences(conn)
            enrich_users_list_with_user_regions(conn)

            # If file is in testing mode in canary dev't
            if using_canary:
                stage_percent = config['canary_params']['users_on_stage']  # noqa
                list_of_admins, list_of_testers = get_list_of_admins_and_testers(conn)
                enrich_users_by_corrected_regions(conn, is_prod, stage_percent)
                # enrich_users_with_admins_and_testers(is_prod, config, list_of_admins, list_of_testers)
                mark_new_records_as_being_processed(conn, is_prod)
                mark_new_comments_as_being_processed(conn, is_prod)

            log_debug_message(admin_user_id)

            # check the matrix: new update - user and initiate sending notifications
            iterate_over_all_users_and_updates(bot_2, is_prod, using_canary, conn)

            # mark all the "new" lines in tables Change Log & Comments as "old"
            mark_new_records_as_processed(conn, is_prod)
            mark_new_comments_as_processed(conn, is_prod)

            # final step – update statistics on how many users received notifications on new searches
            record_notification_statistics(conn)

        # check if there are any notifications remained to be sent
        # TODO: delete try
        try:
            check = conn.execute(
                """
                SELECT search_forum_num, changed_field, new_value, id, change_type FROM change_log 
                WHERE notification_sent is NULL 
                OR notification_sent='s' LIMIT 1; """
            ).fetchall()
            if check:
                logging.info('we checked – there is still something to notify, so we re-initiated this function')
                publish_to_pubsub('topic_for_notification', 're-run from same script')
        except:  # noqa
            pass

        conn.close()
        del new_records_list
        del users_list
        del db
        del conn

    else:
        # for safety sake if Staging will be set without Canary=true
        logging.error('Not able to identify the case: not prod, not stage with canary')
        notify_admin('Not able to identify the case: not prod, not stage with canary')

    if analytics_notif_times:
        len_n = len(analytics_notif_times)
        average = sum(analytics_notif_times) / len_n
        notify_admin('[comp_notif]: Analytics: Search_id {}, Change_id {}, Change_type {}, Mailing_id {}: num of '
                     'messages {}, '
                     'average time {} seconds, total time {} seconds'.format(srch_id, chng_id, chng_type,
                                                                             mailing_id,
                                                                             len_n,
                                                                             round(average, 1),
                                                                             round(sum(analytics_notif_times), 1)))
        analytics_notif_times = []

    publish_to_pubsub('topic_to_send_notifications', 'initiate notifs send out')

    return None
