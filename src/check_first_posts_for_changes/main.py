"""Script does several things:
1. checks if the first posts of the searches were changed
2. FIXME - checks active searches' status (Ищем, НЖ, НП, etc.)
3. checks active searches' visibility (accessible for everyone, restricted to a certain group or permanently deleted).
Updates are either saved in PSQL or send via pub/sub to other scripts"""

import os
import requests
import datetime
import re
import json
import logging
import hashlib
import random

import sqlalchemy
# idea for optimization – to move to psycopg2

from google.cloud import secretmanager
from google.cloud import pubsub_v1


project_id = os.environ["GCP_PROJECT"]
client = secretmanager.SecretManagerServiceClient()
requests_session = requests.Session()
publisher = pubsub_v1.PublisherClient()

bad_gateway_counter = 0


class Search:

    def __init__(self,
                 topic_id=None,
                 start_time=None,
                 folder_id=None,
                 upd_time=None,
                 num_s_in_folder=None,
                 num_of_checks=None):
        self.topic_id = topic_id
        self.start_time = start_time
        self.folder_id = folder_id
        self.upd_time = upd_time
        self.num = num_s_in_folder
        self.checks = num_of_checks


class PercentGroup:

    def __init__(self,
                 n=None,
                 start_percent=None,
                 finish_percent=None,
                 start_num=None,
                 finish_num=None,
                 frequency=None,
                 first_delay=None,
                 searches=None # noqa
                 ):
        searches = []
        self.n = n
        self.sp = start_percent
        self.fp = finish_percent
        self.sn = start_num
        self.fn = finish_num
        self.f = frequency
        self.d = first_delay
        self.s = searches

    def __str__(self):
        days = f' or {int(self.f // 1440)} day(s)' if self.f >= 1440 else f''
        return f'N{self.n: <2}: {self.sp}%–{self.fp}%. Updated every {self.f} minute(s){days}. ' \
               f'First delay = {self.d} minutes. nums {self.sn}-{self.fn}. num of searches {len(self.s)}'


def get_secrets(secret_request):
    """get GCP secret"""

    name = f"projects/{project_id}/secrets/{secret_request}/versions/latest"
    response = client.access_secret_version(name=name)

    return response.payload.data.decode("UTF-8")


def sql_connect():
    """connect to PSQL in GCP"""

    db_user = get_secrets("cloud-postgres-username")
    db_pass = get_secrets("cloud-postgres-password")
    db_name = get_secrets("cloud-postgres-db-name")
    db_conn = get_secrets("cloud-postgres-connection-name")
    db_socket_dir = "/cloudsql"

    db_config = {
        "pool_size": 5,
        "max_overflow": 0,
        "pool_timeout": 0,  # seconds
        "pool_recycle": 120,  # seconds
    }

    pool = sqlalchemy.create_engine(
        sqlalchemy.engine.url.URL(
            "postgresql+pg8000",
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

    return pool


def publish_to_pubsub(topic_name, message):
    """publish a new message to pub/sub"""

    topic_path = publisher.topic_path(project_id, topic_name)
    message_json = json.dumps({'data': {'message': message}, })
    message_bytes = message_json.encode('utf-8')

    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publishing succeeded
        logging.info(f'Pub/sub message to topic {topic_name} with event_id = {publish_future.result()} has '
                     f'been triggered. Content: {message}')

    except Exception as e:
        logging.info(f'Not able to send pub/sub message: {message}')
        logging.exception(e)

    return None


def notify_admin(message):
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub('topic_notify_admin', message)

    return None


def update_one_topic_visibility(search_id):
    """update the status of one search: if it is ok or was deleted or hidden"""

    def check_topic_visibility(search_num):
        """check is the existing search was deleted or hidden"""

        topic_visibility = 'regular'
        bad_gateway = False

        content, site_unavailable = parse_search(search_num)

        if site_unavailable:
            return None, None, None, None

        if content.find('Запрошенной темы не существует.') > -1:
            deleted_trigger = True
            topic_visibility = 'deleted'
        else:
            deleted_trigger = False

        if content.find('Для просмотра этого форума вы должны быть авторизованы') > -1:
            hidden_trigger = True
            topic_visibility = 'hidden'
        else:
            hidden_trigger = False

        logging.info(f'search {search_num} is {topic_visibility}')

        return deleted_trigger, hidden_trigger, bad_gateway, topic_visibility

    del_trig, hid_trig, forum_unavailable, visibility = check_topic_visibility(search_id)
    logging.info(f'Visibility checked for {search_id}: visibility = {visibility}')

    if forum_unavailable:
        return None

    pool = sql_connect()
    with pool.connect() as conn:

        try:
            stmt = sqlalchemy.text("""DELETE FROM search_health_check WHERE search_forum_num=:a;""")
            conn.execute(stmt, a=search_id)

            stmt = sqlalchemy.text("""INSERT INTO search_health_check (search_forum_num, timestamp, status) 
                                      VALUES (:a, :b, :c);""")
            conn.execute(stmt, a=search_id, b=datetime.datetime.now(), c=visibility)

            logging.info(f'Visibility updated for {search_id} and set as {visibility}')
            logging.info('---------------')

        except Exception as e:
            logging.info('exception in update_one_topic_visibility')
            logging.exception(e)

        conn.close()
    pool.dispose()

    return None


def update_visibility_for_one_hidden_topic():
    """check if the hidden search was unhidden"""

    global requests_session

    pool = sql_connect()
    conn = pool.connect()

    try:
        hidden_topic = conn.execute("""
            SELECT h.search_forum_num, s.status_short, s.status 
            FROM search_health_check AS h LEFT JOIN searches AS s 
            ON h.search_forum_num=s.search_forum_num 
            WHERE h.status = 'hidden' ORDER BY RANDOM() LIMIT 1; 
            /*action='get_one_hidden_topic' */;""").fetchone()

        hidden_topic_id = int(hidden_topic[0])
        current_status = hidden_topic[1]
        if current_status in {'Ищем', 'Возобновлен'}:
            logging.info(f'we start checking visibility for topic {hidden_topic_id}')
            update_one_topic_visibility(hidden_topic_id)

    except Exception as e:
        logging.info('exception in update_visibility_for_one_hidden_topic')
        logging.exception(e)

    conn.close()
    pool.dispose()

    return None


def parse_search(search_num):
    """parse the whole search page"""

    global requests_session
    global bad_gateway_counter

    try:
        url = f'https://lizaalert.org/forum/viewtopic.php?t={search_num}'
        r = requests_session.get(url, timeout=10)  # seconds – not sure if it is efficient in this case
        content = r.content.decode("utf-8")
        content = None if content.find('502 Bad Gateway') > 0 else content
        site_unavailable = False if content else True

    except (requests.exceptions.ReadTimeout, Exception) as e:
        logging.info(f'[che_posts]: site unavailable: {e.__class__.__name__}')
        content = None
        site_unavailable = True

    return content, site_unavailable


def get_status_from_content_and_send_to_topic_management(topic_id, act_content):
    """block to check if Status of the search has changed – if so send a pub/sub to topic_management"""

    # get the Title out of page content (intentionally avoid BS4 to make pack slimmer)
    pre_title = re.search(r'<h2 class="topic-title"><a href=.{1,500}</a>', act_content)
    pre_title = pre_title.group() if pre_title else None
    pre_title = re.search(r'">.{1,500}</a>', pre_title[32:]) if pre_title else None
    title = pre_title.group()[2:-4] if pre_title else None

    if not title:
        return None

    # language=regexp
    patterns = [[r'(?i)(^\W{0,2}|(?<=\W)|(найден[аы]?\W{1,3})?)жив[аы]?\W', 'НЖ'],
                [r'(?i)(^\W{0,2}|(?<=\W)|(найден[аы]?\W{1,3})?)погиб(л[иа])?\W', 'НП'],
                [r'(?i).{0,10}заверш.н\W', 'Завершен']]  # [r'(?i).{0,10}пропал.*', 'Ищем'],

    status = None
    for pattern in patterns:
        if re.search(pattern[0], title):
            status = pattern[1]
            break

    if not status:
        return None

    publish_to_pubsub('topic_for_topic_management', {'topic_id': topic_id, 'status': status})

    return None


def update_first_posts_and_statuses():
    """update first posts for searches"""

    def get_list_of_searches():
        """get best list of searches for which first posts should be checked"""

        base_table = []
        base_table_of_objects = []

        pool_2 = sql_connect()
        conn_2 = pool_2.connect()

        try:
            # get the data from sql with the structure:
            # [topic_id, search_start_time, forum_folder_id, search_update_time, number_of_searches_in_folder]
            # search_update_time – is a time of search's first post actualization in SQL
            # number_of_searches_in_folder – is a historical number of searches in SQL assigned to each folder
            raw_sql_extract = conn_2.execute("""
                SELECT 
                    s4.*, s5.count 
                FROM (
                    SELECT 
                        s2.*, s3.timestamp, s3.num_of_checks
                    FROM (
                        SELECT 
                            s0.search_forum_num, s0.search_start_time, s0.forum_folder_id 
                        FROM (
                            SELECT 
                                search_forum_num, search_start_time, forum_folder_id
                            FROM
                                searches 
                            WHERE
                                status_short = 'Ищем'
                        ) s0 
                        LEFT JOIN 
                            search_health_check s1 
                        ON 
                            s0.search_forum_num=s1.search_forum_num 
                        WHERE
                            (s1.status != 'deleted' AND s1.status != 'hidden') OR s1.status IS NULL
                    ) s2 
                    LEFT JOIN 
                    (
                    SELECT 
                        search_id, timestamp, actual, content_hash, num_of_checks 
                    FROM
                        search_first_posts 
                    WHERE
                        actual=TRUE
                    ) s3 
                    ON
                        s2.search_forum_num=s3.search_id
                ) s4 
                LEFT JOIN 
                (
                    SELECT
                        count(*), forum_folder_id
                    FROM
                        searches
                    GROUP BY
                        forum_folder_id
                    ORDER BY
                        count(*) DESC
                ) s5 
                ON 
                    s4.forum_folder_id=s5.forum_folder_id
                LEFT JOIN
                    folders AS f
                ON
                    s4.forum_folder_id = f.folder_id
                WHERE 
                    f.folder_type IS NULL OR f.folder_type = 'searches'
                 ORDER BY 2 DESC
                /*action='get_list_of_searches_for_first_post_and_status_update 2.0' */        
                ;
                """).fetchall()

            # form the list-like table
            if raw_sql_extract:
                for line_2 in raw_sql_extract:
                    new_line = [line_2[0], line_2[1], line_2[3], line_2[5], line_2[4]]
                    new_object = Search(topic_id=line_2[0], start_time=line_2[1], folder_id=line_2[2],
                                        upd_time=line_2[3], num_of_checks=line_2[4], num_s_in_folder=line_2[5])

                    # for blank lines we paste the oldest date
                    if not new_object.upd_time:
                        new_object.upd_time = datetime.datetime(1, 1, 1, 0, 0)
                    if not new_object.checks:
                        new_object.checks = 1
                    base_table.append(new_line)
                    base_table_of_objects.append(new_object)

        except Exception as e2:
            logging.info('exception in get_list_of_searches_for_first_post_update')
            logging.exception(e2)

        conn_2.close()
        pool_2.dispose()

        return base_table_of_objects

    def generate_list_of_search_groups():
        """generate N search groups, groups needed to define which part of all searches will be checked now"""

        percent_step = 7
        list_of_groups = []
        current_percent = 0

        while current_percent < 100:
            n = int(current_percent / percent_step)
            new_group = PercentGroup(n=n,
                                     start_percent=current_percent,
                                     finish_percent=min(100, current_percent + percent_step - 1),
                                     frequency=2 ** n,
                                     first_delay=2 ** (n - 1) - 1 if n != 0 else 0)
            list_of_groups.append(new_group)
            current_percent += percent_step

        return list_of_groups

    def define_which_search_groups_to_be_checked(list_of_groups):
        """gives an output of 2 groups that should be checked for this time"""

        start_time = datetime.datetime(2023, 1, 1, 0, 0, 0)
        curr_minute = int(((datetime.datetime.now() - start_time).total_seconds() / 60) // 1)

        curr_minute_list = []
        for group_2 in list_of_groups:
            if not ((curr_minute - group_2.d) % group_2.f):
                curr_minute_list.append(group_2)
                logging.info(f'Group to be checked {group_2}')

        return curr_minute_list

    def enrich_groups_with_searches(list_of_groups, list_of_s):
        """add searches to the chosen groups"""

        num_of_searches = len(list_of_s)

        for group_2 in list_of_groups:
            group_2.sn = int((group_2.sp * num_of_searches / 100) // 1)
            group_2.fn = min(int(((group_2.fp + 1) * num_of_searches / 100) // 1 - 1), len(list_of_s))

        for j, search in enumerate(list_of_s):
            for group_2 in list_of_groups:
                if group_2.sn <= j <= group_2.fn:
                    group_2.s.append(search)

        return list_of_groups

    def prettify_content(content):
        """remove the irrelevant code from the first page content"""

        # TODO - seems can be much simplified with regex
        # cut the wording of the first post
        start = content.find('<div class="content">')
        content = content[(start + 21):]

        # find the next block and limit the content till this block
        next_block = content.find('<div class="back2top">')
        content = content[:(next_block - 12)]

        # cut out div closure
        fin_div = content.rfind('</div>')
        content = content[:fin_div]

        # cut blank symbols in the end of code
        finish = content.rfind('>')
        content = content[:(finish + 1)]

        # exclude dynamic info – views of the pictures
        patterns = re.findall(r'\) \d+ просмотр(?:а|ов)?', content)
        if patterns:
            for word in patterns:
                content = content.replace(word, ")")

        # exclude dynamic info - token / creation time / sid / etc / footer
        patterns_list = [r'value="\S{10}"',
                         r'value="\S{32}"',
                         r'value="\S{40}"',
                         r'sid=\S{32}&amp;',
                         r'<span class="footer-info"><span title="SQL time:.{120,130}</span></span>'
                         ]

        patterns = []
        for pat in patterns_list:
            patterns += re.findall(pat, content)

        if patterns:
            for word in patterns:
                content = content.replace(word, '')

        return content

    def get_first_post(search_num):
        """parse the first post of search"""

        cont, forum_unavailable = parse_search(search_num)
        not_found = True if cont and re.search(r'Запрошенной темы не существует', cont) else False

        if forum_unavailable or not_found:
            hash_num = None
            return hash_num, cont, forum_unavailable, not_found

        # FIXME – deactivated on Feb 6 2023 because seems it's not correct that this script should check status
        # FIXME – activated on Feb 7 2023 –af far as there were 2 searches w/o status updated
        get_status_from_content_and_send_to_topic_management(search_num, cont)

        cont = prettify_content(cont)

        # craft a hash for this content
        hash_num = hashlib.md5(cont.encode()).hexdigest()

        return hash_num, cont, forum_unavailable, not_found

    def update_first_posts_in_sql(searches_list):
        """TODO"""

        num_of_searches_counter = 0
        num_of_site_errors_counter = 0
        list_of_searches_with_updated_f_posts = []
        pool = sql_connect()
        conn = pool.connect()
        try:
            for line in searches_list:
                num_of_searches_counter += 1
                search_id = line.topic_id
                act_hash, act_content, site_unavailable, topic_not_found = get_first_post(search_id)

                if not site_unavailable and not topic_not_found:

                    # check the latest hash
                    stmt = sqlalchemy.text("""
                            SELECT content_hash, num_of_checks, content from search_first_posts WHERE search_id=:a 
                            AND actual = TRUE;
                            """)
                    raw_data = conn.execute(stmt, a=search_id).fetchone()

                    # if record for this search – exists
                    if raw_data:

                        last_hash = raw_data[0]
                        prev_number_of_checks = raw_data[1]
                        # last_content = raw_data[2]

                        if not prev_number_of_checks:
                            prev_number_of_checks = 1

                        # if record for this search – outdated
                        if act_hash != last_hash:

                            # set all prev records as Actual = False
                            stmt = sqlalchemy.text("""
                                    UPDATE search_first_posts SET actual = FALSE WHERE search_id = :a;
                                    """)
                            conn.execute(stmt, a=search_id)

                            # add new record
                            stmt = sqlalchemy.text("""
                                    INSERT INTO search_first_posts 
                                    (search_id, timestamp, actual, content_hash, content, num_of_checks) 
                                    VALUES (:a, :b, TRUE, :c, :d, :e);
                                    """)
                            conn.execute(stmt, a=search_id, b=datetime.datetime.now(), c=act_hash,
                                         d=act_content, e=1)

                            list_of_searches_with_updated_f_posts.append(search_id)

                        # if record for this search – actual
                        # FIXME – a theory that num_of_checks is not needed anymore
                        """else:
                            # update the number of checks for this search
                            stmt = sqlalchemy.text(""UPDATE search_first_posts SET num_of_checks = :a 
                                                      WHERE search_id = :b AND actual = True;"")
                            conn.execute(stmt, a=(prev_number_of_checks + 1), b=search_id)"""
                        # FIXME ^^^

                    # if record for this search – does not exist – add a new record
                    else:
                        stmt = sqlalchemy.text("""INSERT INTO search_first_posts 
                                                  (search_id, timestamp, actual, content_hash, content, num_of_checks) 
                                                  VALUES (:a, :b, TRUE, :c, :d, :e);""")
                        conn.execute(stmt, a=search_id, b=datetime.datetime.now(), c=act_hash, d=act_content, e=1)

                elif site_unavailable:
                    num_of_site_errors_counter += 1
                    logging.info('forum unavailable'.format(search_id, bad_gateway_counter))
                    if num_of_site_errors_counter > 3:
                        notify_admin(f'were are here - new escape of site unavailability after '
                                     f'{num_of_site_errors_counter} attempts.')
                        break

                elif topic_not_found:
                    update_one_topic_visibility(search_id)

        except Exception as e:
            logging.info('exception in update_first_posts_and_statuses')
            logging.exception(e)

        conn.close()
        pool.dispose()

        logging.info(f'first posts checked for {num_of_searches_counter} searches')

        return list_of_searches_with_updated_f_posts

    global bad_gateway_counter
    global requests_session

    list_of_searches = get_list_of_searches()
    groups_list_all = generate_list_of_search_groups()
    groups_list_now = define_which_search_groups_to_be_checked(groups_list_all)
    groups_list_now = enrich_groups_with_searches(groups_list_now, list_of_searches)
    searches_list_now = [line for group in groups_list_now for line in group.s]

    if not groups_list_now:
        return None

    list_of_searches_with_updated_first_posts = update_first_posts_in_sql(searches_list_now)

    if not list_of_searches_with_updated_first_posts:
        return None

    publish_to_pubsub('topic_for_first_post_processing', list_of_searches_with_updated_first_posts)

    return None


def main(event, context): # noqa
    """main function"""

    # to avoid function invocation except when it was initiated by scheduler (and pub/sub message was not doubled)
    if datetime.datetime.now().second > 5:
        return None

    global bad_gateway_counter
    bad_gateway_counter = 0

    # BLOCK 1. for checking if the first posts were changed
    update_first_posts_and_statuses()

    # BLOCK 2. small bonus: check one of topics, which has visibility='hidden' to check if it was not unhidden later.
    # It is done in this script only because there's no better place. Ant these are circa 40 hidden topics at all.
    update_visibility_for_one_hidden_topic()

    if bad_gateway_counter > 3:
        publish_to_pubsub('topic_notify_admin', f'[che_posts]: Bad Gateway {bad_gateway_counter} times')

    # Close the open session
    requests_session.close()

    return None
