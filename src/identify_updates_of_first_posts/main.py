"""Check if the first post of the search was updated in terms of field trips and coordinates change.
Result to be recorded into Change_log and triggered another script identify_updates_of_folders."""

import ast
import copy
import datetime
import difflib
import json
import logging
import re
from typing import Any, Dict, Optional

import requests
import sqlalchemy
from bs4 import BeautifulSoup

from _dependencies.commons import Topics, publish_to_pubsub, setup_google_logging, sqlalchemy_get_pool
from _dependencies.content import clean_up_content_2
from _dependencies.misc import generate_random_function_id, notify_admin, process_pubsub_message

setup_google_logging()

requests_session = requests.Session()


def sql_connect() -> sqlalchemy.engine.Engine:
    return sqlalchemy_get_pool(5, 30)


def get_the_list_of_coords_out_of_text(initial_text: str):
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
        soup = BeautifulSoup(initial_text, features='html.parser')
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
                                line_3[2] = '5. boxed coord'

        # remove duplicates
        if list_of_all_coord_mentions:
            for line in list_of_all_coord_mentions:
                if line not in resulting_list:
                    resulting_list.append(line)

    # output [[lat_1, lon_1, type_1], ... ,[lat_N, lon_N, type_N]]
    return resulting_list


def compose_diff_message(curr_list, prev_list):
    message = ''

    if not curr_list or not prev_list:
        return message, [], []

    diff = difflib.unified_diff(prev_list, curr_list, lineterm='')

    list_of_deletions = []
    list_of_additions = []

    for line in diff:
        if line[0] == '-':
            addition = re.sub(r'^[\s+-]+', '', line)
            if addition:
                list_of_deletions.append(addition)
        elif line[0] == '+':
            addition = re.sub(r'^[\s+-]+', '', line)
            if addition:
                list_of_additions.append(addition)

    if list_of_deletions:
        message += 'Удалено:\n<s>'
        for line in list_of_deletions:
            message += f'{line}\n'
        message += '</s>'

    if list_of_additions:
        if message:
            message += '\n'
        message += 'Добавлено:\n'
        for line in list_of_additions:
            # majority of coords in RU: lat in [30-80], long in [20-180]
            updated_line = re.sub(r'0?[3-8]\d\.\d{1,10}.{0,3}([2-9]\d|1\d{2})\.\d{1,10}', r'<code>\g<0></code>', line)
            message += f'{updated_line}\n'

    return message, list_of_deletions, list_of_additions


def process_first_page_comparison(conn, search_id: int, first_page_content_prev: str, first_page_content_curr: str):
    """compare first post content to identify any diffs"""

    # check the latest status on this search
    sql_text = sqlalchemy.text("""SELECT display_name, status, family_name, age, status
                                      FROM searches WHERE search_forum_num=:a;""")

    what_is_saved_in_psql = conn.execute(sql_text, a=search_id).fetchone()

    if not what_is_saved_in_psql:
        logging.info('first page comparison failed – nothing is searches psql table')
        return None, None

    try:
        # FIXME – just to double-check
        print(f' we print that what_is_saved_in_psql = {what_is_saved_in_psql}')
        print(f' we print "not what_is_saved_in_psql" = {not what_is_saved_in_psql}')
        print(f' we print "what_is_saved_in_psql == None" = {what_is_saved_in_psql is None}')
        print(f' we print "what_is_saved_in_psql == Null" = {what_is_saved_in_psql == "Null"}')
        # FIXME ^^^

        display_name, status, name, age, status_old = list(what_is_saved_in_psql)
    except Exception as e:
        notify_admin('this strange exception happened, check [ide_posts]')
        logging.exception(e)
        return None, None

    # updates are made only for non-finished searches
    if status != 'Ищем':
        return None, None

    prev_clean_content = clean_up_content_2(first_page_content_prev)
    curr_clean_content = clean_up_content_2(first_page_content_curr)

    message, list_of_del, list_of_add = compose_diff_message(curr_clean_content, prev_clean_content)

    # case when there is only 1 line changed and the change is in one blank space or letter – we don't notify abt it
    if list_of_del and list_of_add and len(list_of_del) == 1 and len(list_of_add) == 1:
        diff = difflib.ndiff(list_of_del[0], list_of_add[0])
        changes = ''
        for line in diff:
            if line[0] in {'-', '+'}:
                changes += line[1:]
        changes = re.sub(r'\s', '', changes)  # changes in blank lines are irrelevant
        changes = re.sub(r'\D', '', changes, count=1)  # changes for only one letter – irrelevant (but not for digit)
        if not changes:
            try:
                notify_admin(
                    f'[ide_posts]: IGNORED MINOR CHANGE: \ninit message: {message}'
                    f'\ndel: {list_of_del}\nadd: {list_of_add}'
                )
            except:  # noqa
                notify_admin('THIS ERROR')
            return '', None

    message_dict = {'del': list_of_del, 'add': list_of_add, 'message': message}

    return message, message_dict


def save_new_record_into_change_log(
    conn, search_id: int, coords_change_list: list, changed_field: str, change_type: int
) -> int:
    """save the coordinates change into change_log"""

    stmt = sqlalchemy.text(
        """INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, change_type)
        values (:a, :b, :c, :d, :e) RETURNING id;"""
    )

    raw_data = conn.execute(
        stmt, a=datetime.datetime.now(), b=search_id, c=changed_field, d=str(coords_change_list), e=change_type
    ).fetchone()
    change_log_id = raw_data[0]

    return change_log_id


def parse_search_folder(search_num):
    """parse search's folder number"""

    folder = None

    url = 'https://lizaalert.org/forum/viewtopic.php?t=' + str(search_num)
    r = requests_session.get(url)  # 10 seconds – do we need it in this script?
    content = r.content.decode('utf-8')

    soup = BeautifulSoup(content, features='html.parser')
    spans = soup.find_all('span', {'class': 'crumb'})

    for line in spans:
        try:
            folder = int(line['data-forum-id'])
        except:  # noqa
            pass

    return folder


def get_compressed_first_post(initial_text: str):
    """convert the initial html text of first post into readable string (for reading in SQL)"""

    compressed_string = ''

    if initial_text:
        text_to_soup = BeautifulSoup(initial_text, features='html.parser')

        basic_text_string = text_to_soup.text
        basic_text_string = basic_text_string.replace('\n', ' ')

        # width of text block in symbols
        block_width = 50

        list_from_string = [
            basic_text_string[i : i + block_width] for i in range(0, len(basic_text_string), block_width)
        ]

        for list_line in list_from_string:
            compressed_string += list_line + '\n'

    return compressed_string


def split_text_to_deleted_and_regular_parts(text: str):
    """split text into two strings: one for deleted (line-through) text and second for regular"""

    soup = BeautifulSoup(text, features='html.parser')

    soup_without_deleted = copy.copy(soup)
    deleted_text = soup_without_deleted.find_all('span', {'style': 'text-decoration:line-through'})
    for case in deleted_text:
        case.decompose()
    non_deleted_text = str(soup_without_deleted)

    deleted_list = [
        item.getText(strip=False) for item in soup.find_all('span', {'style': 'text-decoration:line-through'})
    ]

    deleted_text = '\n'.join(deleted_list)

    # TODO: debug
    print(f'deleted text = {deleted_text}')
    print(f'non-deleted text = {non_deleted_text}')
    # TODO: debug

    return deleted_text, non_deleted_text


def get_field_trip_details_from_text(text: str):
    """return the dict with 'filed trip' parameters for the search's text"""

    """resulting_field_trip_dict = {'vyezd': False,  # True for vyezd
                                     'sbor': False,  # True for sbor

                                     'now': True,  # True for now of and False for future
                                     'urgent': False,  # True for urgent
                                     'secondary': False,  # True for secondary

                                     'coords': None,  # [lat, lon] for the most relevant pair of coords

                                     'date_and_time': None,  # time of filed trip
                                     'address': None,  # place of filed trip (not coords)
                                     }"""

    class FieldTrip:
        def __init__(
            self,
            field_trip=False,
            camp=False,
            now=False,
            urgent=False,
            repeat=False,
            coordinates=None,
            date_and_time=None,
            place=None,
            blocks=None,
        ):
            coordinates = []
            blocks = []
            self.trip = field_trip
            self.camp = camp
            self.now = now
            self.urgent = urgent
            self.repeat = repeat
            self.coords = coordinates
            self.time = date_and_time
            self.place = place
            self.b = blocks

    class Block:
        def __init__(self, type=None, title=None, time=None, place=None, coords=None):
            self.type = type
            self.title = title
            self.time = time
            self.place = place
            self.coords = coords

    field_trip_vyezd = re.findall(
        r'(?i)(?:внимание.{0,3}|)'
        r'(?:скоро.{0,3}|срочно.{0,3}|)'
        r'(?:планируется.{0,3}|ожидается.{0,3}|готовится.{0,3}|запланирован.{0,3}|)'
        r'(?:повторный.{0,3}|срочный.{0,3}|активный.{0,3})?'
        r'(?:выезд|вылет|cбор на поиск|сбор)'
        r'(?:.{0,3}срочно|сейчас|)'
        r'(?:.{0,3}планируется|.{0,3}ожидается|.{0,3}готовится|.{0,3}запланирован|)'
        r'(?:.{0,4}\d\d\.\d\d\.\d\d(?:\d\d|)|)'
        r'.{0,3}(?:[\r\n]+|.){0,1000}',
        text,
    )

    # TODO: to be deleted
    field_trip_sbor = re.findall(
        r'(?:место.{0,3}|время.{0,3}|координаты.{0,3}(?:места.{0,3}|)|)сбор(?:а|)', text.lower()
    )
    # TODO: to be deleted

    resulting_field_trip_dict = {'vyezd': False}

    trip = FieldTrip()

    # Update the parameters of the output_dict
    # vyezd
    if field_trip_vyezd:
        resulting_field_trip_dict['vyezd'] = True
        trip.trip = True

    # TODO: to delete
    # sbor
    if field_trip_sbor:
        resulting_field_trip_dict['sbor'] = True
        trip.camp = True

    # now / urgent / secondary
    for phrase in field_trip_vyezd:
        # now
        if re.findall(r'(планируется|ожидается|готовится)', phrase.lower()):
            resulting_field_trip_dict['now'] = False
            resulting_field_trip_dict['planned'] = True

        # urgent
        if re.findall(r'срочн', phrase.lower()):
            resulting_field_trip_dict['urgent'] = True

        # secondary
        if re.findall(r'повторн', phrase.lower()):
            resulting_field_trip_dict['secondary'] = True

    # coords
    coords_curr_full_list = get_the_list_of_coords_out_of_text(text)
    # format [[lat_1, lon_1, type_1], ... ,[lat_N, lon_N, type_N]]

    # TODO: temp debug
    print(f'BBB: coords_curr_full_list={coords_curr_full_list}')
    # TODO: temp debug

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

    # TODO: temp debug
    print(f'BBB: lat, lon={lat}, {lon}')
    # TODO: temp debug

    if lat is not None and lon is not None:
        resulting_field_trip_dict['coords'] = [lat, lon]

    # date_and_time and address
    for line_ft in field_trip_vyezd:
        list_of_lines = line_ft.splitlines()
        for list_line in list_of_lines:
            r = re.search(r'(?i)(?:^штаб[^а][^\sсвернут]|.{0,10}(?:адрес|место|точка сбора)).{0,100}', list_line)
            if r:
                resulting_field_trip_dict['address'] = re.sub(re.compile('<.*?>'), '', r.group())

            r = re.search(
                r'(?i)^(?!.*мест. сбор).{0,10}(?:время|сбор.{1,3}(?:в\s|к\s|с\s|.{1,10}\d{2}.{1,3}\d{2})).{0,100}',
                list_line,
            )
            if r:
                resulting_field_trip_dict['date_and_time'] = re.sub(re.compile('<.*?>'), '', r.group())

    return resulting_field_trip_dict


def save_function_into_register(conn, context, start_time, function_id, change_log_ids):
    """save current function into functions_registry"""

    try:
        event_id = context.event_id
        json_of_params = json.dumps({'ch_id': change_log_ids})

        sql_text = sqlalchemy.text("""INSERT INTO functions_registry
                                                  (event_id, time_start, cloud_function_name, function_id,
                                                  time_finish, params)
                                                  VALUES (:a, :b, :c, :d, :e, :f)
                                                  /*action='save_ide_f_posts_function' */;""")
        conn.execute(
            sql_text,
            a=event_id,
            b=start_time,
            c='identify_updates_of_f_posts',
            d=function_id,
            e=datetime.datetime.now(),
            f=json_of_params,
        )
        logging.info(f'function {function_id} was saved in functions_registry')

    except Exception as e:
        logging.info(f'function {function_id} was NOT ABLE to be saved in functions_registry')
        logging.exception(e)

    return None


def main(event, context):  # noqa
    """key function"""

    function_id = generate_random_function_id()
    analytics_func_start = datetime.datetime.now()

    # receive a list of searches where first post was updated
    message_from_pubsub = process_pubsub_message(event)
    list_of_updated_searches = ast.literal_eval(str(message_from_pubsub))

    change_log_ids = []

    if list_of_updated_searches:
        pool = sql_connect()
        with pool.connect() as conn:
            try:
                list_of_folders_with_upd_searches = []

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

                    logging.info(f'topic id {search_id} has an update of first post:')
                    logging.info(f'first page content prev: {first_page_content_prev}')
                    logging.info(f'first page content curr: {first_page_content_curr}')

                    # TODO: DEBUG try
                    try:
                        if first_page_content_curr and first_page_content_prev:
                            # check the difference b/w first posts for current and previous version
                            message_on_first_posts_diff, diff_dict = process_first_page_comparison(
                                conn, search_id, first_page_content_prev, first_page_content_curr
                            )
                            if message_on_first_posts_diff:
                                message_on_first_posts_diff = str(diff_dict)
                                change_log_id = save_new_record_into_change_log(
                                    conn, search_id, message_on_first_posts_diff, 'topic_first_post_change', 8
                                )
                                change_log_ids.append(change_log_id)

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

                    save_function_into_register(conn, context, analytics_func_start, function_id, change_log_ids)

                    publish_to_pubsub(Topics.topic_to_run_parsing_script, str(list_of_folders_with_upd_searches))
                    message_for_pubsub = {
                        'triggered_by_func_id': function_id,
                        'text': str(list_of_folders_with_upd_searches),
                    }
                    publish_to_pubsub(Topics.topic_for_notification, message_for_pubsub)

            except Exception as e:
                logging.info('exception in main function')
                logging.exception(e)

            conn.close()
        pool.dispose()
    requests_session.close()

    return 'ok'
