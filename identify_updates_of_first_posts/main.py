import os
import base64
import json
import logging
import ast
import re
import requests

import sqlalchemy
from bs4 import BeautifulSoup

from google.cloud import pubsub_v1
from google.cloud import secretmanager

project_id = os.environ["GCP_PROJECT"]
client = secretmanager.SecretManagerServiceClient()
publisher = pubsub_v1.PublisherClient()
requests_session = requests.Session()


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
        "pool_size": 30,
        "max_overflow": 0,
        "pool_timeout": 10,  # seconds
        "pool_recycle": 0,  # seconds
    }

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

    return pool


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


def publish_to_pubsub(topic_name, message):
    """publish a new message to pub/sub"""

    # global project_id

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


def get_the_list_of_coords_out_of_text(initial_text):
    """get all the pairs of coordinates in the given text"""

    list_of_all_coord_mentions = []
    resulting_list = []

    if initial_text:
        # remove blank spaces and newlines in the initial text
        initial_text = initial_text.replace('<br>', ' ')
        initial_text = initial_text.replace('\n', ' ')

        # get the list of all mentions of coords at all
        # majority of coords in RU: lat in [40-80], long in [20-180], expected minimal format = XX.XXX
        list_of_all_coords = re.findall(r'0?[3-8]\d\.[\d]{1,10}.{0,10}(?:0,1)?[2-8]\d\.[\d]{1,10}', initial_text)
        if list_of_all_coords:
            for line in list_of_all_coords:
                nums = re.findall(r'0?[2-8]\d\.[\d]{1,10}', line)
                list_of_all_coord_mentions.append([float(nums[0]), float(nums[1]), '2. coordinates w/o word coord'])

        # get the list of all mentions with word 'Coordinates'
        list_of_all_mentions_of_word_coord = re.findall(r'[Кк]оординат[^ор].{0,150}', initial_text)
        if list_of_all_mentions_of_word_coord:
            for line in list_of_all_mentions_of_word_coord:
                list_of_coords = re.findall(r'0?[3-8]\d\.[\d]{1,10}.{0,10}(?:0,1)?[2-8]\d\.[\d]{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.[\d]{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '1. coordinates w/ word coord'

        # get the deleted coordinates
        soup = BeautifulSoup(initial_text, features="html.parser")
        deleted_text = soup.find_all('span', {'style': 'text-decoration:line-through'})
        if deleted_text:
            for line in deleted_text:
                line = str(line)
                list_of_coords = re.findall(r'0?[3-8]\d\.[\d]{1,10}.{0,10}(?:0,1)?[2-8]\d\.[\d]{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.[\d]{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '3. deleted coord'

        # TODO: can be simplified by removing duplication with deleted coords
        # get the boxed coordinates (like in https://lizaalert.org/forum/viewtopic.php?f=276&t=54417 )
        boxed_text = soup.find_all('dl', {'class': 'codebox'})
        if boxed_text:
            for line in boxed_text:
                line = str(line)
                list_of_coords = re.findall(r'0?[3-8]\d\.[\d]{1,10}.{0,10}(?:0,1)?[2-8]\d\.[\d]{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.[\d]{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '4. boxed coord'

        # remove duplicates
        if list_of_all_coord_mentions:
            for line in list_of_all_coord_mentions:
                if line not in resulting_list:
                    resulting_list.append(line)

    return resulting_list


def get_resulting_message_on_coordinates_change(prev_coords, curr_coords):
    """compare two versions of coordinates for same search and generate the outgoing message"""

    message = ''

    if prev_coords and curr_coords:

        # combine the fill list of coords
        full_list = []
        for line in prev_coords:
            full_list.append([line[0], line[1], 0, 0])
        for line in curr_coords:
            full_list.append([line[0], line[1], 0, 0])

        # remove duplicates
        resulting_list = []
        if full_list:
            for line in full_list:
                if line not in resulting_list:
                    resulting_list.append(line)

        # fill in the new list
        # structure: lat, lon, prev_desc, curr_desc
        if resulting_list:
            for line in resulting_list:
                if prev_coords:
                    for line_2 in prev_coords:
                        if line[0] == line_2[0] and line[1] == line_2[1]:
                            line[2] = int(line_2[2][0])
                if curr_coords:
                    for line_2 in curr_coords:
                        if line[0] == line_2[0] and line[1] == line_2[1]:
                            line[3] = int(line_2[2][0])

        # filter the list from unchanged records
        filtered_list = []
        if resulting_list:
            for line in resulting_list:
                if line[2] != line[3]:
                    filtered_list.append(line)

        # generate message
        if filtered_list:
            for line in filtered_list:
                if line[2] in {1, 2} and line[3] in {0, 3, 4}:
                    message += ' * координаты {}, {} более не актуальны!\n'.format(line[0], line[1])
                elif line[2] == 0 and line[3] in {1, 2}:
                    message += ' * новые координыты поиска! {}, {}\n'.format(line[0], line[1])
                elif line[2] in {3, 4} and line[3] in {1, 2}:
                    message += ' * координыты {}, {} вновь актуальны!\n'.format(line[0], line[1])

    return message


def get_the_search_status_out_of_text(initial_text):
    """get the status of coordinates in the given text"""

    list_of_all_coord_mentions = []
    resulting_list = []

    if initial_text:
        # remove blank spaces and newlines in the initial text
        initial_text = initial_text.replace('<br>', ' ')
        initial_text = initial_text.replace('\n', ' ')

        # get the list of all mentions of coords at all
        # majority of coords in RU: lat in [40-80], long in [20-180], expected minimal format = XX.XXX
        list_of_all_coords = re.findall(r'0?[3-8]\d\.[\d]{1,10}.{0,10}(?:0,1)?[2-8]\d\.[\d]{1,10}', initial_text)
        if list_of_all_coords:
            for line in list_of_all_coords:
                nums = re.findall(r'0?[2-8]\d\.[\d]{1,10}', line)
                list_of_all_coord_mentions.append([float(nums[0]), float(nums[1]), '2. coordinates w/o word coord'])

        # get the list of all mentions with word 'Coordinates'
        list_of_all_mentions_of_word_coord = re.findall(r'[Кк]оординат[^ор].{0,150}', initial_text)
        if list_of_all_mentions_of_word_coord:
            for line in list_of_all_mentions_of_word_coord:
                list_of_coords = re.findall(r'0?[3-8]\d\.[\d]{1,10}.{0,10}(?:0,1)?[2-8]\d\.[\d]{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.[\d]{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '1. coordinates w/ word coord'

        # get the deleted coordinates
        soup = BeautifulSoup(initial_text, features="html.parser")
        deleted_text = soup.find_all('span', {'style': 'text-decoration:line-through'})
        if deleted_text:
            for line in deleted_text:
                line = str(line)
                list_of_coords = re.findall(r'0?[3-8]\d\.[\d]{1,10}.{0,10}(?:0,1)?[2-8]\d\.[\d]{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.[\d]{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '3. deleted coord'

        # TODO: can be simplified by removing duplication with deleted coords
        # get the boxed coordinates (like in https://lizaalert.org/forum/viewtopic.php?f=276&t=54417 )
        boxed_text = soup.find_all('dl', {'class': 'codebox'})
        if boxed_text:
            for line in boxed_text:
                line = str(line)
                list_of_coords = re.findall(r'0?[3-8]\d\.[\d]{1,10}.{0,10}(?:0,1)?[2-8]\d\.[\d]{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.[\d]{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '4. boxed coord'

        # remove duplicates
        if list_of_all_coord_mentions:
            for line in list_of_all_coord_mentions:
                if line not in resulting_list:
                    resulting_list.append(line)

    return resulting_list


def parse_search_folder(search_num):
    """parse search's folder number"""

    folder = None

    url = 'https://lizaalert.org/forum/viewtopic.php?t=' + str(search_num)
    r = requests_session.get(url)  # 10 seconds – do we need it in this script?
    content = r.content.decode("utf-8")

    soup = BeautifulSoup(content, features="html.parser")
    spans = soup.find_all('span', {'class': 'crumb'})

    for line in spans:
        try:
            folder = int(line['data-forum-id'])
        except: # noqa
            pass

    return folder


def get_compressed_first_post(initial_text):
    """convert the initial html text of first post into readable string (for reading in SQL)"""

    compressed_string = ''

    if initial_text:

        text_to_soup = BeautifulSoup(initial_text, features="html.parser")

        basic_text_string = text_to_soup.text
        basic_text_string = basic_text_string.replace('\n', ' ')

        # width of text block in symbols
        x = 50

        list_from_string = [basic_text_string[i: i + x] for i in range(0, len(basic_text_string), x)]

        for list_line in list_from_string:
            compressed_string += list_line + '\n'

    return compressed_string


def get_message_on_field_trip(text):
    """return the 'filed trip' message for the search's text"""

    field_trip_vyezd = re.findall(r'(?:внимание.{0,3}|)'
                                  r'(?:скоро.{0,3}|)'
                                  r'(?:планируется.{0,3}|ожидается.{0,3}|готовится.{0,3}|запланирован.{0,3}|)'
                                  r'(?:повторный.{0,3}|срочный.{0,3}|активный.{0,3})?'
                                  r'выезд'
                                  r'(?:.{0,3}срочно|)'
                                  r'(?:.{0,3}планируется|.{0,3}ожидается|.{0,3}готовится|.{0,3}запланирован|)'
                                  r'(?:.{0,3}\d\d\.\d\d\.\d\d(?:\d\d|)|)',
                                  text.lower())

    field_trip_sbor = re.findall(r'(?:место.{0,3}|время.{0,3}|координаты.{0,3}(?:места.{0,3}|)|)сбор(?:а|)',
                                 text.lower())

    total_list = field_trip_sbor + field_trip_vyezd
    output_message = None

    if total_list:
        if field_trip_vyezd:
            output_message = field_trip_vyezd[0].capitalize()
        else:
            output_message = 'Внимание, выезд!'

    return output_message


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


def main(event, context): # noqa
    """key function"""

    message_from_pubsub = process_pubsub_message(event)
    list_of_updated_searches = ast.literal_eval(message_from_pubsub)
    db = sql_connect()

    list_of_folders_with_upd_searches = []

    if list_of_updated_searches:

        with db.connect() as conn:

            for search_id in list_of_updated_searches:

                # get the Current First Page Content
                sql_text = sqlalchemy.text("""
                SELECT content, content_compact FROM search_first_posts WHERE search_id=:a AND actual = True;
                """)
                raw_data = conn.execute(sql_text, a=search_id).fetchone()
                first_page_content_curr = raw_data[0]
                first_page_content_curr_compact = raw_data[1]

                # save compact first page content
                if not first_page_content_curr_compact:
                    content_compact = get_compressed_first_post(first_page_content_curr)
                    sql_text = sqlalchemy.text("""
                                    UPDATE search_first_posts SET content_compact=:a 
                                    WHERE search_id=:b AND actual = True;
                                    """)
                    conn.execute(sql_text, a=content_compact, b=search_id)

                # some searches are not opening in the forum - and it's not Bot error
                # if not first_page_content_curr:
                #    logging.error('there is no Curr First Page content in SQL for {}.'.format(search_id))

                # get the Previous First Page Content
                sql_text = sqlalchemy.text("""
                               SELECT content 
                               FROM search_first_posts 
                               WHERE search_id=:a AND actual=False 
                               ORDER BY timestamp DESC;
                               """)
                first_page_content_prev = conn.execute(sql_text, a=search_id).fetchone()[0]

                # case below - is not an error
                # if not first_page_content_prev:
                #    logging.error('there is no Prev First Page content in SQL for {}.'.format(search_id))

                # TODO: just debug
                logging.info(first_page_content_curr)
                logging.info(first_page_content_prev)

                coords_curr = get_the_list_of_coords_out_of_text(first_page_content_curr)
                coords_prev = get_the_list_of_coords_out_of_text(first_page_content_prev)

                # save the coords snapshot
                sql_text = sqlalchemy.text("""
                                UPDATE search_first_posts SET coords=:a WHERE search_id=:b AND actual = True;
                                """)
                conn.execute(sql_text, a=str(coords_curr), b=search_id)

                # TODO: debug
                if coords_prev:
                    publish_to_pubsub('topic_notify_admin', '-----> {}: {}'.format(search_id, str(coords_curr)))

                # compose a DEBUG message for admin
                msg = get_resulting_message_on_coordinates_change(coords_prev, coords_curr)
                if msg:
                    msg = '[ide_post]: FIRST PAGE / Coords: поиск {}: \n'.format(search_id) + msg
                    publish_to_pubsub('topic_notify_admin', msg)

                # TODO DEBUG try
                try:
                    sql_text = sqlalchemy.text("""
                                    SELECT family_name, age FROM searches WHERE search_forum_num=:a;
                                    """)
                    raw_data = conn.execute(sql_text, a=search_id).fetchone()
                    name = raw_data[0]
                    age = raw_data[1]
                    link = 'https://lizaalert.org/forum/viewtopic.php?t=' + str(search_id)
                    msg_2 = ''
                    msg_2 += '<a href="' + link + '">'
                    msg_2 += name
                    if name[0].isupper() and age and age != 0:
                        msg_2 += ' '
                        msg_2 += age_writer(age)
                    msg_2 += '</a>'

                    publish_to_pubsub('topic_notify_admin', '>>>>>>>testing: ' + msg_2)

                    if first_page_content_curr:
                        field_trip_curr = get_message_on_field_trip(first_page_content_curr)
                    else:
                        field_trip_curr = None
                    if first_page_content_prev:
                        field_trip_prev = get_message_on_field_trip(first_page_content_prev)
                    else:
                        field_trip_prev = None

                    if not field_trip_prev and field_trip_curr:
                        message_field_trip = field_trip_curr + '\nПоиск ' + msg_2
                        publish_to_pubsub('topic_notify_admin', message_field_trip)
                        publish_to_pubsub('topic_notify_admin', first_page_content_prev[:3900])

                except Exception as e:
                    logging.error(e)
                    publish_to_pubsub('topic_notify_admin', '[ide_posts]: ERROR: notify Field Trip Failed: '
                                      + repr(e)[:3900])

                # save folder number for the search that has an update
                folder_num = parse_search_folder(search_id)
                new_line = [folder_num, None] if folder_num else None

                if new_line and new_line not in list_of_folders_with_upd_searches:
                    list_of_folders_with_upd_searches.append(new_line)

            # evoke 'parsing script' to check in the folders with updated searches have any update
            if list_of_folders_with_upd_searches:
                publish_to_pubsub('topic_notify_admin', f'[ide_post]: {str(list_of_folders_with_upd_searches)}')
                publish_to_pubsub('topic_to_run_parsing_script', str(list_of_folders_with_upd_searches))

    # Close the open session
    requests_session.close()

    return None
