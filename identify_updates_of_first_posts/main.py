"""Check if the first post of the search was updated in terms of field trips and coordinates change.
Result to be recorded into Change_log and triggered another script identify_updates_of_folders."""

import datetime
import os
import base64
import json
import logging
import ast
import re
import copy
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
            "postgresql+pg8000",
            username=db_user,
            password=db_pass,
            database=db_name,
            query={
                "unix_sock": f"{db_socket_dir}/{db_conn}/.s.PGSQL.5432"
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

    logging.info(f'LOGGING-INFO: incoming Pub/Sub message: {message_in_ascii}')

    return message_in_ascii


def publish_to_pubsub(topic_name, message):
    """publish a new message to pub/sub"""

    topic_path = publisher.topic_path(project_id, topic_name)
    message_json = json.dumps({'data': {'message': message}, })
    message_bytes = message_json.encode('utf-8')

    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publishing succeeded
        logging.info(f'Sent pub/sub message: {message}')

    except Exception as e:
        logging.error('Not able to send pub/sub message')
        logging.exception(e)

    return None


def notify_admin(message):
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub('topic_notify_admin', message)

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
        # majority of coords in RU: lat in [40-80], long in [20-180], expected minimal format = XX.X
        list_of_all_coords = re.findall(r'0?[3-8]\d\.\d{1,10}.{0,10}(?:0,1)?[2-8]\d\.\d{1,10}', initial_text)
        if list_of_all_coords:
            for line in list_of_all_coords:
                nums = re.findall(r'0?[2-8]\d\.\d{1,10}', line)
                list_of_all_coord_mentions.append([float(nums[0]), float(nums[1]), '2. coordinates w/o word coord'])

        # get the list of all mentions with word 'Coordinates'
        list_of_all_mentions_of_word_coord = re.findall(r'[Кк]оординат[^ор].{0,150}', initial_text)
        if list_of_all_mentions_of_word_coord:
            for line in list_of_all_mentions_of_word_coord:
                list_of_coords = re.findall(r'0?[3-8]\d\.\d{1,10}.{0,10}(?:0,1)?[2-8]\d\.\d{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.\d{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '1. coordinates w/ word coord'

        # get the deleted coordinates
        soup = BeautifulSoup(initial_text, features="html.parser")
        deleted_text = soup.find_all('span', {'style': 'text-decoration:line-through'})
        if deleted_text:
            for line in deleted_text:
                line = str(line)
                list_of_coords = re.findall(r'0?[3-8]\d\.\d{1,10}.{0,10}(?:0,1)?[2-8]\d\.\d{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.\d{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '3. deleted coord'

        # TODO: can be simplified by removing duplication with deleted coords
        # get the boxed coordinates (like in https://lizaalert.org/forum/viewtopic.php?f=276&t=54417 )
        boxed_text = soup.find_all('dl', {'class': 'codebox'})
        if boxed_text:
            for line in boxed_text:
                line = str(line)
                list_of_coords = re.findall(r'0?[3-8]\d\.\d{1,10}.{0,10}(?:0,1)?[2-8]\d\.\d{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.\d{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '4. boxed coord'

        # remove duplicates
        if list_of_all_coord_mentions:
            for line in list_of_all_coord_mentions:
                if line not in resulting_list:
                    resulting_list.append(line)

    # output [[lat_1, lon_1, type_1], ... ,[lat_N, lon_N, type_N]]
    return resulting_list


def get_resulting_message_on_coordinates_change(prev_coords, curr_coords):
    """compare two versions of coordinates for same search and generate the outgoing message"""

    message = ''
    filtered_list = []

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
        if resulting_list:
            for line in resulting_list:
                if line[2] != line[3]:
                    filtered_list.append(line)

        # generate message
        if filtered_list:
            for line in filtered_list:
                if line[2] in {1, 2} and line[3] in {0, 3, 4}:
                    message += f' * координаты {line[0]}, {line[1]} более не актуальны!\n'
                elif line[2] == 0 and line[3] in {1, 2}:
                    message += f' * новые координаты поиска! {line[0]}, {line[1]}\n'
                elif line[2] in {3, 4} and line[3] in {1, 2}:
                    message += f' * координаты {line[0]}, {line[1]} вновь актуальны!\n'

    # structure of filtered_list: lat, lon, prev_desc, curr_desc
    return filtered_list, message


def process_coords_comparison(conn, search_id, first_page_content_curr, first_page_content_prev):
    """compare first post content to identify diff in coords"""

    # get the lists of coordinates & context: curr vs prev
    # format [[lat_1, lon_1, type_1], ... ,[lat_N, lon_N, type_N]]
    coords_curr = get_the_list_of_coords_out_of_text(first_page_content_curr)
    coords_prev = get_the_list_of_coords_out_of_text(first_page_content_prev)

    # TODO: DEBUG temp
    logging.info(f'curr coords: {coords_curr}')
    logging.info(f'prev coords: {coords_prev}')
    # TODO: DEBUG temp

    # save the curr coords snapshot
    sql_text = sqlalchemy.text("""
                    UPDATE search_first_posts SET coords=:a WHERE search_id=:b AND actual = True;
                    """)
    conn.execute(sql_text, a=str(coords_curr), b=search_id)

    # TODO: temp debug
    if coords_prev and coords_curr and coords_prev != coords_curr:
        publish_to_pubsub('topic_notify_admin', f'[ide_post]: prev coords {search_id}: {coords_prev}')
        publish_to_pubsub('topic_notify_admin', f'[ide_post]: curr coords {search_id}: {coords_curr}')
    logging.info(f'[ide_post]: prev coords {search_id}: {coords_prev}')
    logging.info(f'[ide_post]: curr coords {search_id}: {coords_curr}')
    # TODO: temp debug

    # get a list of changed coordinates
    # TODO: + temp DEBUG message for admin
    # structure of coords_change_list: lat, lon, prev_desc, curr_desc
    coords_change_list, msg = get_resulting_message_on_coordinates_change(coords_prev, coords_curr)
    if msg:
        msg = f'[ide_post]: coords change {search_id}: \n{msg}'
        publish_to_pubsub('topic_notify_admin', msg)

    # structure of coords_change_list: lat, lon, prev_desc, curr_desc
    return coords_change_list


def process_field_trips_comparison(conn, search_id, first_page_content_prev, first_page_content_curr):
    """compare first post content to identify diff in field trips"""

    field_trips_dict = {'case': None}

    # check the latest status on this search
    sql_text = sqlalchemy.text("""SELECT family_name, age, status_short FROM searches WHERE search_forum_num=:a;""")
    name, age, status_short = conn.execute(sql_text, a=search_id).fetchone()

    # updated are made only for non-finished searches
    if status_short == 'Ищем':

        # TODO: this block is only for DEBUG - to be deleted
        link = f'https://lizaalert.org/forum/viewtopic.php?t={search_id}'
        age_wording = age_writer(age) if age else None
        age_info = f' {age_wording}' if (name[0].isupper() and age and age != 0) else ''
        msg_2 = f'{name}{age_info}, {search_id}, {link}'
        # publish_to_pubsub('topic_notify_admin', f'[ide_post]: testing: {msg_2}')
        # TODO: this block is only for DEBUG - to be deleted

        # split the texts of the first posts into deleted and regular blocks
        text_prev_del, text_prev_reg = split_text_to_deleted_and_regular_parts(first_page_content_prev)
        text_curr_del, text_curr_reg = split_text_to_deleted_and_regular_parts(first_page_content_curr)

        # get field_trip-related context from texts
        # format:
        # context_prev_del = check_changes_of_field_trip(text_prev_del)
        context_prev_reg = get_field_trip_details_from_text(text_prev_reg)
        context_curr_del = get_field_trip_details_from_text(text_curr_del)
        context_curr_reg = get_field_trip_details_from_text(text_curr_reg)

        field_trips_dict = {
            # 'prev_del': context_prev_del,  # not used
            'prev_reg': context_prev_reg,  # TODO: to be deleted
            'curr_del': context_curr_del,  # TODO: to be deleted
            'curr_reg': context_curr_reg,  # TODO: to be deleted

            'case': None  # can be: None / add / drop / change
            # 'urgent': False,
            # 'now': True,
            # 'secondary': False,
            # 'date_and_time_curr': None,
            # 'address_curr': None,
            # 'coords_curr': None

        }

        # define the CASE (None / add / drop / change)
        # CASE 1 "add"
        if (context_curr_reg['sbor'] or context_curr_reg['vyezd']) and \
                not context_prev_reg['sbor'] and \
                not context_prev_reg['vyezd']:

            field_trips_dict['case'] = 'add'

            field_trips_dict['urgent'] = context_curr_reg['urgent']
            field_trips_dict['now'] = context_curr_reg['now']
            field_trips_dict['secondary'] = context_curr_reg['secondary']
            if 'coords' in context_curr_reg:
                field_trips_dict['coords'] = context_curr_reg['coords']

            field_trips_dict['date_and_time_curr'] = context_curr_reg['datetime']
            field_trips_dict['address_curr'] = context_curr_reg['address']

        # CASE 2 "drop"
        if not context_curr_reg['sbor'] and \
                not context_curr_reg['vyezd'] and \
                (context_prev_reg['sbor'] or context_prev_reg['vyezd']):
            field_trips_dict['case'] = 'drop'

        # CASE 3 "change"
        # CASE 3.1 "was nothing in prev and here's already cancelled one in curr"
        if (context_curr_reg['sbor'] or context_curr_reg['vyezd']) and \
                not context_prev_reg['sbor'] and \
                not context_prev_reg['vyezd'] and \
                (context_curr_del['sbor'] or context_curr_del['vyezd']):
            field_trips_dict['case'] = 'change'

            field_trips_dict['date_and_time_curr'] = context_curr_reg['datetime']
            field_trips_dict['address_curr'] = context_curr_reg['address']

            if 'coords' in context_curr_reg:
                field_trips_dict['coords_curr'] = context_curr_reg['coords']

        # CASE 3.2 "there was something which differs in prev and curr"
        if (context_curr_reg['sbor'] or context_curr_reg['vyezd']) and \
                (context_prev_reg['sbor'] or context_prev_reg['vyezd']) and \
                (context_curr_reg['original_text'] != context_prev_reg['original_text'] or
                 context_curr_reg['now'] != context_prev_reg['now'] or
                 context_curr_reg['secondary'] != context_prev_reg['secondary']):
            field_trips_dict['case'] = 'change'

            field_trips_dict['date_and_time_curr'] = context_curr_reg['datetime']
            field_trips_dict['address_curr'] = context_curr_reg['address']

            if 'coords' in context_curr_reg:
                field_trips_dict['coords_curr'] = context_curr_reg['coords']

        # TODO: temp debug
        notify_admin(f'[ide_posts]:{msg_2}\n\n{field_trips_dict}')
        logging.info(f'{msg_2}\n\n{field_trips_dict}')
        # TODO: temp debug

    return field_trips_dict


def save_new_record_into_change_log(conn, search_id, coords_change_list, changed_field, change_type):
    """save the coordinates change into change_log"""

    stmt = sqlalchemy.text(
        """INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, change_type)
        values (:a, :b, :c, :d, :e);"""
    )

    conn.execute(stmt,
                 a=datetime.datetime.now(),
                 b=search_id,
                 c=changed_field,
                 d=str(coords_change_list),
                 e=change_type
                 )

    return None


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
        list_of_all_coords = re.findall(r'0?[3-8]\d\.\d{1,10}.{0,10}(?:0,1)?[2-8]\d\.\d{1,10}', initial_text)
        if list_of_all_coords:
            for line in list_of_all_coords:
                nums = re.findall(r'0?[2-8]\d\.\d{1,10}', line)
                list_of_all_coord_mentions.append([float(nums[0]), float(nums[1]), '2. coordinates w/o word coord'])

        # get the list of all mentions with word 'Coordinates'
        list_of_all_mentions_of_word_coord = re.findall(r'[Кк]оординат[^ор].{0,150}', initial_text)
        if list_of_all_mentions_of_word_coord:
            for line in list_of_all_mentions_of_word_coord:
                list_of_coords = re.findall(r'0?[3-8]\d\.\d{1,10}.{0,10}(?:0,1)?[2-8]\d\.\d{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.\d{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '1. coordinates w/ word coord'

        # get the deleted coordinates
        soup = BeautifulSoup(initial_text, features="html.parser")
        deleted_text = soup.find_all('span', {'style': 'text-decoration:line-through'})
        if deleted_text:
            for line in deleted_text:
                line = str(line)
                list_of_coords = re.findall(r'0?[3-8]\d\.\d{1,10}.{0,10}(?:0,1)?[2-8]\d\.\d{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.\d{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '3. deleted coord'

        # TODO: can be simplified by removing duplication with deleted coords
        # get the boxed coordinates (like in https://lizaalert.org/forum/viewtopic.php?f=276&t=54417 )
        boxed_text = soup.find_all('dl', {'class': 'codebox'})
        if boxed_text:
            for line in boxed_text:
                line = str(line)
                list_of_coords = re.findall(r'0?[3-8]\d\.\d{1,10}.{0,10}(?:0,1)?[2-8]\d\.\d{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.\d{1,10}', line_2)
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
        except:  # noqa
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
        block_width = 50

        list_from_string = [basic_text_string[i: i + block_width] for i in
                            range(0, len(basic_text_string), block_width)]

        for list_line in list_from_string:
            compressed_string += list_line + '\n'

    return compressed_string


def split_text_to_deleted_and_regular_parts(text):
    """split text into two strings: one for deleted (line-through) text and second for regular"""

    soup = BeautifulSoup(text, features="html.parser")

    soup_without_deleted = copy.copy(soup)
    deleted_text = soup_without_deleted.find_all('span', {'style': 'text-decoration:line-through'})
    for case in deleted_text:
        case.decompose()
    non_deleted_text = str(soup_without_deleted)

    deleted_list = [
        item.getText(strip=True) for item in soup.find_all('span', {'style': 'text-decoration:line-through'})
    ]

    deleted_text = '\n'.join(deleted_list)

    # TODO: debug
    print(f'deleted text = {deleted_text}')
    print(f'non-deleted text = {non_deleted_text}')
    # TODO: debug

    return deleted_text, non_deleted_text


def get_field_trip_details_from_text(text):
    """return the dict with 'filed trip' parameters for the search's text"""

    field_trip_vyezd = re.findall(r'(?i)(?:внимание.{0,3}|)'
                                  r'(?:скоро.{0,3}|срочно.{0,3}|)'
                                  r'(?:планируется.{0,3}|ожидается.{0,3}|готовится.{0,3}|запланирован.{0,3}|)'
                                  r'(?:повторный.{0,3}|срочный.{0,3}|активный.{0,3})?'
                                  r'(?:выезд|вылет)'
                                  r'(?:.{0,3}срочно|сейчас|)'
                                  r'(?:.{0,3}планируется|.{0,3}ожидается|.{0,3}готовится|.{0,3}запланирован|)'
                                  r'(?:.{0,3}\d\d\.\d\d\.\d\d(?:\d\d|)|)'
                                  r'.{0,3}(?:[\r\n]+|.){0,1000}',
                                  text)

    field_trip_sbor = re.findall(r'(?:место.{0,3}|время.{0,3}|координаты.{0,3}(?:места.{0,3}|)|)сбор(?:а|)',
                                 text.lower())

    resulting_field_trip_dict = {'vyezd': False,  # True for vyezd
                                 'sbor': False,  # True for sbor

                                 'now': True,  # True for now of and False for future
                                 'urgent': False,  # True for urgent
                                 'secondary': False,  # True for secondary

                                 'coords': None,  # [lat, lon] for the most relevant pair of coords

                                 'datetime': None,  # time of filed trip
                                 'address': None,  # place of filed trip (not coords)

                                 # TODO: block to be deleted
                                 'original_prefix': '',  # for 'Внимание срочный выезд'
                                 'prettified_prefix': '',  # for 'Внимание срочный выезд'
                                 'original_text': '',  # All the matched cases by regex
                                 'prettified_text': ''  # Prettified to be shown as one text.
                                 # TODO: block to be deleted

                                 }

    # Update the parameters of the output_dict
    # vyezd
    if field_trip_vyezd:
        resulting_field_trip_dict['vyezd'] = True
        resulting_field_trip_dict['original_text'] = '. '.join(field_trip_vyezd)
        for line in field_trip_vyezd:
            prettified_line = line.lower().capitalize()
            # TODO: other cosmetics are also expected: e.g.
            #  making all delimiters as blank spaces except after 'внимание'
            resulting_field_trip_dict['prettified_text'] += f'{prettified_line}\n'

    # sbor
    if field_trip_sbor:
        resulting_field_trip_dict['sbor'] = True
        resulting_field_trip_dict['original_text'] = '. '.join(field_trip_sbor)
        for line in field_trip_sbor:
            prettified_line = line.lower().capitalize()
            # TODO: other cosmetics are also expected: e.g.
            #  making all delimiters as blank spaces except after 'внимание'
            resulting_field_trip_dict['prettified_text'] += f'{prettified_line}\n'

    # now / urgent  /secondary
    for phrase in field_trip_vyezd:

        # now
        if re.findall(r'(планируется|ожидается|готовится)', phrase.lower()):
            resulting_field_trip_dict['now'] = False

        # urgent
        if re.findall(r'срочн', phrase.lower()):
            resulting_field_trip_dict['urgent'] = True

        # secondary
        if re.findall(r'повторн', phrase.lower()):
            resulting_field_trip_dict['secondary'] = True

    # coords
    coords_curr_full_list = get_the_list_of_coords_out_of_text(text)
    # format [[lat_1, lon_1, type_1], ... ,[lat_N, lon_N, type_N]]

    # we just need to get curr coords of type 1 or 2 (with world coords or without)
    lat, lon = None, None
    if coords_curr_full_list:
        for line in coords_curr_full_list:
            if line[2][0] == '1':
                lat, lon = line[0], line[1]
                break
        if lat is None and lon is None:
            for line in coords_curr_full_list:
                if line[2][0] == '2':
                    lat, lon = line[0], line[1]
                    break

    if lat is not None and lon is not None:
        resulting_field_trip_dict['coords'] = [lat, lon]

    # datetime and address
    for line_ft in field_trip_vyezd:
        list_of_lines = line_ft.splitlines()
        for list_line in list_of_lines:
            r = re.search(r'(?i)(?:^штаб[^а][^\sсвернут]|.{0,10}(?:адрес|место)).{0,100}', list_line)
            resulting_field_trip_dict['address'] = r.group() if r else ''

            r = re.search(
                r'(?i)^(?!.*мест. сбор).{0,10}(?:время|сбор.{1,3}(?:в\s|к\s|с\s|.{1,10}\d{2}.{1,3}\d{2})).{0,100}',
                list_line)
            resulting_field_trip_dict['datetime'] = r.group() if r else ''

    return resulting_field_trip_dict


def age_writer(age):
    """compose an age string with the right form of years in Russian"""

    if age:
        a = age // 100
        b = (age - a * 100) // 10
        c = age - a * 100 - b * 10
        if c == 1 and b != 1:
            wording = str(age) + " год"
        elif c in {2, 3, 4} and b != 1:
            wording = str(age) + " года"
        else:
            wording = str(age) + " лет"
    else:
        wording = ''

    return wording


def main(event, context):  # noqa
    """key function"""

    # receive a list of searches where first post was updated
    message_from_pubsub = process_pubsub_message(event)
    list_of_updated_searches = ast.literal_eval(message_from_pubsub)

    list_of_folders_with_upd_searches = []

    if list_of_updated_searches:

        with sql_connect().connect() as conn:

            for search_id in list_of_updated_searches:

                # get the Current First Page Content
                sql_text = sqlalchemy.text("""
                SELECT content, content_compact FROM search_first_posts WHERE search_id=:a AND actual = True;
                """)
                raw_data = conn.execute(sql_text, a=search_id).fetchone()
                first_page_content_curr = raw_data[0]
                first_page_content_curr_compact = raw_data[1]

                # TODO: why we're doing it in this script but not in che_posts??
                # save compact first page content
                if not first_page_content_curr_compact:
                    content_compact = get_compressed_first_post(first_page_content_curr)
                    sql_text = sqlalchemy.text("""
                                    UPDATE search_first_posts SET content_compact=:a 
                                    WHERE search_id=:b AND actual = True;
                                    """)
                    conn.execute(sql_text, a=content_compact, b=search_id)

                # get the Previous First Page Content
                sql_text = sqlalchemy.text("""
                               SELECT content 
                               FROM search_first_posts 
                               WHERE search_id=:a AND actual=False 
                               ORDER BY timestamp DESC;
                               """)
                first_page_content_prev = conn.execute(sql_text, a=search_id).fetchone()[0]

                # TODO: temp debug
                logging.info(f'first page content prev: {first_page_content_prev}')
                logging.info(f'first page content curr: {first_page_content_curr}')
                # TODO: temp debug

                # TODO: DEBUG try
                try:
                    if first_page_content_curr and first_page_content_prev:

                        # get the final list of parameters on field trip (new, change or drop)
                        field_trips_dict = process_field_trips_comparison(conn, search_id, first_page_content_prev,
                                                                          first_page_content_curr)

                        # Save Field Trip (incl potential Coords change) into Change_log
                        if field_trips_dict['case'] == 'add':
                            save_new_record_into_change_log(conn, search_id,
                                                            str(field_trips_dict), 'field_trip_new', 5)

                        elif field_trips_dict['case'] in {'drop', 'change'}:

                            # Check if coords changed as well during Field Trip
                            # structure: lat, lon, prev_desc, curr_desc
                            coords_change_list = process_coords_comparison(conn, search_id, first_page_content_curr,
                                                                           first_page_content_prev)
                            field_trips_dict['coords'] = str(coords_change_list)

                            save_new_record_into_change_log(conn, search_id,
                                                            str(field_trips_dict), 'field_trip_change', 6)

                        else:

                            # structure_list: lat, lon, prev_desc, curr_desc
                            coords_change_list = process_coords_comparison(conn, search_id, first_page_content_curr,
                                                                           first_page_content_prev)
                            if coords_change_list:
                                save_new_record_into_change_log(conn, search_id,
                                                                coords_change_list, 'coords_change', 7)

                except Exception as e:
                    logging.info('[ide_posts]: Error fired during output_dict creation.')
                    logging.exception(e)
                    notify_admin('[ide_posts]: Error fired during output_dict creation.')

                # save folder number for the search that has an update
                folder_num = parse_search_folder(search_id)
                new_line = [folder_num, None] if folder_num else None

                if new_line and new_line not in list_of_folders_with_upd_searches:
                    list_of_folders_with_upd_searches.append(new_line)

            # evoke 'parsing script' to check if the folders with updated searches have any update
            if list_of_folders_with_upd_searches:
                # notify_admin(f'[ide_post]: {str(list_of_folders_with_upd_searches)}')
                publish_to_pubsub('topic_to_run_parsing_script', str(list_of_folders_with_upd_searches))

    # Close the open session
    requests_session.close()

    return None
