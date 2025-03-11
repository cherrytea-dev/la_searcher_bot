"""Script takes as input the list of recently-updated forum folders. Then it parses first 20 searches (aka topics)
and saves into PSQL if there are any updates"""

from dataclasses import dataclass

import ast
import copy
import logging
import re
from datetime import datetime
from typing import Any, List, Optional, Tuple, Union

import requests
import sqlalchemy
from bs4 import BeautifulSoup, SoupStrainer  # noqa
from google.cloud import storage
from google.cloud.storage.blob import Blob
from psycopg2.extensions import connection
from sqlalchemy.engine.base import Engine

from _dependencies.commons import (
    ChangeType,
    TopicType,
    Topics,
    publish_to_pubsub,
    setup_google_logging,
    sqlalchemy_get_pool,
)
from _dependencies.misc import generate_random_function_id, make_api_call, notify_admin, process_pubsub_message_v3
from identify_updates_of_topics._utils.database import (
    _delete_search,
    _get_current_searches,
    _get_current_snapshots_list,
    _get_prev_searches,
    _update_search_activities,
    _update_search_managers,
    _write_change_log,
    _write_search,
    get_geolocation_form_psql,
    get_the_list_of_ignored_folders,
    rewrite_snapshot_in_sql,
    save_function_into_register,
    save_geolocation_in_psql,
    save_last_api_call_time_to_psql,
    save_place_in_psql,
    update_coordinates_in_db,
    write_comment,
)
from identify_updates_of_topics._utils.external_api import (
    get_coordinates_from_address_by_osm,
    get_coordinates_from_address_by_yandex,
    rate_limit_for_api,
)
from identify_updates_of_topics._utils.forum import (
    define_start_time_of_search,
    parse_search_profile,
    visibility_check,
)
from identify_updates_of_topics._utils.parse import (
    parse_address_from_title,
    profile_get_managers,
    profile_get_type_of_activity,
)
from identify_updates_of_topics._utils.topics_commons import ChangeLogLine, SearchSummary, get_requests_session

setup_google_logging()


class CloudStorage:
    BUCKET_NAME = 'bucket_for_snapshot_storage'

    def read_folder_hash(self, folder_num: str) -> str | None:
        try:
            blob = self._set_cloud_storage(folder_num)
            contents_as_bytes = blob.download_as_string()
            contents = str(contents_as_bytes, 'utf-8')
        except:  # noqa
            contents = None

        return contents

    def write_folder_hash(self, data: Any, folder_num: str) -> None:
        blob = self._set_cloud_storage(folder_num)
        blob.upload_from_string(data)

    def _set_cloud_storage(self, folder_num: str) -> Blob:
        """sets the basic parameters for connection to txt file in cloud storage, which stores searches snapshots"""

        if isinstance(folder_num, int) or folder_num == 'geocode':
            blob_name = str(folder_num) + '.txt'
        else:
            blob_name = folder_num
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(self.BUCKET_NAME)
        blob = bucket.blob(blob_name)

        return blob


def get_coordinates_by_address(db: Engine, address: str) -> Tuple[None, None]:
    """convert address string into a pair of coordinates"""

    try:
        # check if this address was already geolocated and saved to psql
        saved_status, lat, lon, saved_geocoder = get_geolocation_form_psql(db, address)

        if lat and lon:
            return lat, lon

        elif saved_status == 'fail' and saved_geocoder == 'yandex':
            return None, None

        elif not saved_status:
            # when there's no saved record
            rate_limit_for_api(db=db, geocoder='osm')
            lat, lon = get_coordinates_from_address_by_osm(address)
            api_call_time_saved = save_last_api_call_time_to_psql(db=db, geocoder='osm')
            logging.info(f'{api_call_time_saved=}')

            if lat and lon:
                saved_status = 'ok'
                save_geolocation_in_psql(db, address, saved_status, lat, lon, 'osm')
            else:
                saved_status = 'fail'

        if saved_status == 'fail' and (saved_geocoder == 'osm' or not saved_geocoder):
            # then we need to geocode with yandex
            rate_limit_for_api(db=db, geocoder='yandex')
            lat, lon = get_coordinates_from_address_by_yandex(address)
            api_call_time_saved = save_last_api_call_time_to_psql(db=db, geocoder='yandex')
            logging.info(f'{api_call_time_saved=}')

            if lat and lon:
                saved_status = 'ok'
            else:
                saved_status = 'fail'
            save_geolocation_in_psql(db, address, saved_status, lat, lon, 'yandex')

        return lat, lon

    except Exception as e:
        logging.info('TEMP - LOC - New getting coordinates from title failed')
        logging.exception(e)
        notify_admin('ERROR: major geocoding script failed')

    return None, None


def parse_coordinates_of_search(db: connection, search_num) -> tuple[float, float, str]:
    """finds coordinates of the search"""

    requests_session = get_requests_session()

    # DEBUG - function execution time counter
    func_start = datetime.now()

    url_to_topic = f'https://lizaalert.org/forum/viewtopic.php?t={search_num}'

    lat = 0
    lon = 0
    coord_type = ''
    search_code_blocks = None
    title = None

    try:
        r = requests_session.get(url_to_topic)  # noqa
        if not visibility_check(r, search_num):
            return [0, 0, '']
    except Exception as e:
        logging.exception('Can`t get topic %s', url_to_topic)
        return [0, 0, '']

    try:
        soup = BeautifulSoup(r.content, features='html.parser')

        # parse title
        title_code = soup.find('h2', {'class': 'topic-title'})
        title = title_code.text

        # open the first post
        search_code_blocks = soup.find('div', 'content')

        if not search_code_blocks:
            return [lat, lon, coord_type]

        # removing <br> tags
        for e in search_code_blocks.findAll('br'):
            e.extract()

    except Exception as e:
        logging.info(f'unable to parse a specific thread with address {url_to_topic} error is {repr(e)}')

    if search_code_blocks:
        # FIRST CASE = THERE ARE COORDINATES w/ a WORD Coordinates
        lat, lon, coord_type = parse_coords_case_1(search_code_blocks)

        # SECOND CASE = THERE ARE COORDINATES w/o a WORD Coordinates
        if lat == 0:
            # make an independent variable
            lat, lon, coord_type = _parse_coords_case_2(search_code_blocks)

        # THIRD CASE = DELETED COORDINATES
        if lat == 0:
            # make an independent variable
            lat, lon, coord_type = _parse_coords_case_3(search_code_blocks)

    # FOURTH CASE = COORDINATES FROM ADDRESS
    if lat == 0:
        try:
            address = parse_address_from_title(title)
            if address:
                save_place_in_psql(db, address, search_num)
                lat, lon = get_coordinates_by_address(db, address)
                if lat and lon:
                    coord_type = '4. coordinates by address'
            else:
                logging.info(f'No address was found for search {search_num}, title {title}')
        except Exception as e5:
            logging.exception('DBG.P.42.EXC')

    # DEBUG - function execution time counter
    func_finish = datetime.now()
    func_execution_time_ms = func_finish - func_start
    logging.info(f'the coordinates for {search_num=} are defined as {lat}, {lon}, {coord_type}')
    logging.debug(f'DBG.P.5.parse_coordinates() exec time: {func_execution_time_ms}')

    return lat, lon, coord_type


def parse_coords_case_1(search_code_blocks: BeautifulSoup) -> tuple[float, float, str]:
    lat, lon, coord_type = 0, 0, ''
    try:
        # make an independent variable
        a = copy.copy(search_code_blocks)

        # remove a text with strike-through
        b = a.find_all('span', {'style': 'text-decoration:line-through'})
        for i in range(len(b)):
            b[i].decompose()

            # preparing a list of 100-character strings which starts with Coord mentioning
        e = []
        i = 0
        f = str(a).lower()

        while i < len(f):
            if f[i:].find('коорд') > 0:
                d = i + f[i:].find('коорд')
                e.append(f[d : (d + 100)])
                if d == 0 or d == -1:
                    i = len(f)
                else:
                    i = d + 1
            else:
                i = len(f)

            # extract exact numbers & match if they look like coordinates
        for i in range(len(e)):
            g = [float(s) for s in re.findall(r'-?\d+\.?\d*', e[i])]
            if len(g) > 1:
                for j in range(len(g) - 1):
                    try:
                        # Majority of coords in RU: lat in [40-80], long in [20-180], expected min format = XX.XXX
                        if (
                            3 < (g[j] // 10) < 8
                            and len(str(g[j])) > 5
                            and 1 < (g[j + 1] // 10) < 19
                            and len(str(g[j + 1])) > 5
                        ):
                            lat = g[j]
                            lon = g[j + 1]
                            coord_type = '1. coordinates w/ word coord'
                    except Exception as e2:
                        logging.exception('DBG.P.36.EXC. Coords-1:')

    except Exception as e:
        logging.exception('Can`t get coorditates from search_code_blocks')
    return lat, lon, coord_type


def _parse_coords_case_3(search_code_blocks: BeautifulSoup) -> tuple[float, float, str]:
    lat, lon, coord_type = 0, 0, ''

    a = copy.copy(search_code_blocks)

    try:
        # get a text with strike-through
        a = a.find_all('span', {'style': 'text-decoration:line-through'})
        if a:
            for line in a:
                b = re.sub(r'\n\s*\n', r' ', line.get_text().strip(), flags=re.M)
                c = re.sub(r'\n', r' ', b)
                g = [float(s) for s in re.findall(r'-?\d+\.?\d*', c)]
                if len(g) > 1:
                    for j in range(len(g) - 1):
                        try:
                            # Majority of coords in RU: lat in [40-80], long in [20-180],
                            # expected minimal format = XX.XXX
                            if (
                                3 < (g[j] // 10) < 8
                                and len(str(g[j])) > 5
                                and 1 < (g[j + 1] // 10) < 19
                                and len(str(g[j + 1])) > 5
                            ):
                                lat = g[j]
                                lon = g[j + 1]
                                coord_type = '3. deleted coord'
                        except Exception as e2:
                            logging.info('DBG.P.36.EXC. Coords-1:')
                            logging.exception(e2)
    except Exception as e:
        logging.info('exception:')
        logging.exception(e)
        pass
    return lat, lon, coord_type


def _parse_coords_case_2(search_code_blocks: BeautifulSoup) -> tuple[float, float, str]:
    lat, lon, coord_type = 0, 0, ''
    a = copy.copy(search_code_blocks)

    try:
        # remove a text with strike-through
        b = a.find_all('span', {'style': 'text-decoration:line-through'})
        for i in range(len(b)):
            b[i].decompose()

            # removing <span> tags
        for e in a.findAll('span'):
            e.replace_with(e.text)

            # removing <img> tags
        for e in a.findAll('img'):
            e.extract()

            # removing <a> tags
        for e in a.findAll('a'):
            e.extract()

            # removing <strong> tags
        for e in a.findAll('strong'):
            e.replace_with(e.text)

            # converting to string
        b = re.sub(r'\n\s*\n', r' ', a.get_text().strip(), flags=re.M)
        c = re.sub(r'\n', r' ', b)
        g = [float(s) for s in re.findall(r'-?\d+\.?\d*', c)]
        if len(g) > 1:
            for j in range(len(g) - 1):
                try:
                    # Majority of coords in RU: lat in [40-80], long in [20-180], expected min format = XX.XXX
                    if (
                        3 < (g[j] // 10) < 8
                        and len(str(g[j])) > 5
                        and 1 < (g[j + 1] // 10) < 19
                        and len(str(g[j + 1])) > 5
                    ):
                        lat = g[j]
                        lon = g[j + 1]
                        coord_type = '2. coordinates w/o word coord'
                except Exception as e2:
                    logging.exception('DBG.P.36.EXC. Coords-2:')
    except Exception as e:
        logging.info('Exception 2')
        logging.exception(e)
        pass
    return lat, lon, coord_type


def update_coordinates(db: Engine, list_of_search_objects: list[SearchSummary]) -> None:
    """Record search coordinates to PSQL"""

    for search in list_of_search_objects:
        search_id = search.topic_id
        search_status = search.new_status

        if search_status not in {'Ищем', 'СТОП'}:
            continue

        logging.info(f'search coordinates should be saved for {search_id=}')
        coords = parse_coordinates_of_search(db, search_id)

        update_coordinates_in_db(db, search_id, coords)

    return None


def sql_connect() -> sqlalchemy.engine.Engine:
    return sqlalchemy_get_pool(5, 120)


@dataclass
class ForumFolderContentItem:
    search_title: str
    search_id: int
    search_replies_num: int
    start_datetime: Any


class ForumClient:
    def _get_folder_content(self, folder_id) -> bytes:
        requests_session = get_requests_session()
        url = f'https://lizaalert.org/forum/viewforum.php?f={folder_id}'
        resp = requests_session.get(url, timeout=10)  # for every folder - req'd daily at night forum update # noqa
        resp.raise_for_status()
        return resp.content

    def get_folder_content(self, folder_id: int) -> list[ForumFolderContentItem]:
        content = self._get_folder_content(folder_id)
        only_tag = SoupStrainer('div', {'class': 'forumbg'})
        soup = BeautifulSoup(content, features='lxml', parse_only=only_tag)
        search_code_blocks = soup.find_all('dl', 'row-item')
        del soup  # trying to free up memory

        summaries: list[ForumFolderContentItem] = []
        for i, data_block in enumerate(search_code_blocks):
            # First block is always not one we want
            if i == 0:
                continue

            # In rare cases there are aliases from other folders, which have static titles – and we're avoiding them
            if str(data_block).find('<dl class="row-item topic_moved">') > -1:
                continue

            # Current block which contains everything regarding certain search
            search_title_block = data_block.find('a', 'topictitle')
            # rare case: cleaning [size][b]...[/b][/size] tags
            search_title = re.sub(r'\[/?(b|size.{0,6}|color.{0,10})]', '', search_title_block.next_element)
            search_id = int(re.search(r'(?<=&t=)\d{2,8}', search_title_block['href']).group())
            search_replies_num = int(data_block.find('dd', 'posts').next_element)
            start_datetime = define_start_time_of_search(data_block)

            summaries.append(ForumFolderContentItem(search_title, search_id, search_replies_num, start_datetime))

        del search_code_blocks

        return summaries


def parse_one_folder(db: Engine, folder_id) -> Tuple[List, List[SearchSummary]]:
    """parse forum folder with searches' summaries"""

    topic_type_dict = {
        'search': TopicType.search_regular,
        'search reverse': TopicType.search_reverse,
        'search patrol': TopicType.search_patrol,
        'search training': TopicType.search_training,
        'event': TopicType.event,
    }

    # TODO - "topics_summary_in_folder" – is an old type of list, which was deprecated as an outcome of this script,
    #  now we need to delete it completely
    topics_summary_in_folder = []
    titles_and_num_of_replies = []
    folder_summary: list[SearchSummary] = []
    current_datetime = datetime.now()
    forum_client = ForumClient()
    folder_content_items = forum_client.get_folder_content(folder_id)
    try:
        for forum_search_item in folder_content_items:
            data = {'title': forum_search_item.search_title}
            try:
                title_reco_response = make_api_call('title_recognize', data)  # TODO can use local call in tests

                if (
                    title_reco_response
                    and 'status' in title_reco_response.keys()
                    and title_reco_response['status'] == 'ok'
                ):
                    title_reco_dict = title_reco_response['recognition']
                else:
                    title_reco_dict = {'topic_type': 'UNRECOGNIZED'}

                logging.info(f'{title_reco_dict=}')

                # NEW exclude non-relevant searches
                if title_reco_dict['topic_type'] in {
                    'search',
                    'search training',
                    'search reverse',
                    'search patrol',
                    'event',
                }:
                    # FIXME – 06.11.2023 – work to delete function "define_family_name_from_search_title_new"
                    if title_reco_dict['topic_type'] == 'event':
                        person_fam_name = None
                    else:
                        try:
                            person_fam_name = title_reco_dict['persons']['total_name']  # noqa
                        except Exception as ex:
                            logging.exception(ex)
                            notify_admin(repr(ex))
                            person_fam_name = 'БВП'
                    # FIXME ^^^

                    search_summary_object = SearchSummary(
                        parsed_time=current_datetime,
                        topic_id=forum_search_item.search_id,
                        title=forum_search_item.search_title,
                        start_time=forum_search_item.start_datetime,
                        num_of_replies=forum_search_item.search_replies_num,
                        name=person_fam_name,
                        folder_id=folder_id,
                    )
                    search_summary_object.topic_type = title_reco_dict['topic_type']

                    search_summary_object.topic_type_id = topic_type_dict[search_summary_object.topic_type]

                    if 'persons' in title_reco_dict.keys():
                        if 'total_display_name' in title_reco_dict['persons'].keys():
                            search_summary_object.display_name = title_reco_dict['persons']['total_display_name']
                        if 'age_min' in title_reco_dict['persons'].keys():
                            search_summary_object.age_min = title_reco_dict['persons']['age_min']
                            search_summary_object.age = title_reco_dict['persons']['age_min']  # Due to the field
                            # "age" in searches which is integer, so we cannot indicate a range
                        if 'age_max' in title_reco_dict['persons'].keys():
                            search_summary_object.age_max = title_reco_dict['persons']['age_max']

                    if 'status' in title_reco_dict.keys():
                        search_summary_object.new_status = title_reco_dict['status']
                        search_summary_object.status = title_reco_dict['status']

                    if 'locations' in title_reco_dict.keys():
                        list_of_location_cities = [x['address'] for x in title_reco_dict['locations']]
                        list_of_location_coords = []
                        for location_city in list_of_location_cities:
                            city_lat, city_lon = get_coordinates_by_address(db, location_city)
                            if city_lat and city_lon:
                                list_of_location_coords.append([city_lat, city_lon])
                        search_summary_object.locations = list_of_location_coords

                    folder_summary.append(search_summary_object)

                    search_summary = [
                        current_datetime,
                        forum_search_item.search_id,
                        search_summary_object.status,
                        forum_search_item.search_title,
                        '',
                        forum_search_item.start_datetime,
                        forum_search_item.search_replies_num,
                        search_summary_object.age_min,
                        person_fam_name,
                        folder_id,
                    ]
                    topics_summary_in_folder.append(search_summary)

                    parsed_wo_date = [forum_search_item.search_title, forum_search_item.search_replies_num]
                    titles_and_num_of_replies.append(parsed_wo_date)

            except Exception as e:
                logging.info(f'TEMP - THIS BIG ERROR HAPPENED, {data=}')
                notify_admin(f'TEMP - THIS BIG ERROR HAPPENED, {data=}, {type(data)=}')
                logging.error(e)
                logging.exception(e)

    # To catch timeout once a day in the night
    except (requests.exceptions.Timeout, ConnectionResetError, Exception) as e:
        logging.exception(e)
        topics_summary_in_folder = []
        folder_summary = []

    logging.info(f'folder = {folder_id}, old_topics_summary = {topics_summary_in_folder}')

    return titles_and_num_of_replies, folder_summary


def parse_and_write_one_comment(db: Engine, search_num, comment_num: int) -> bool:
    """parse all details on a specific comment in topic (by sequence number)"""

    requests_session = get_requests_session()

    comment_url = f'https://lizaalert.org/forum/viewtopic.php?&t={search_num}&start={comment_num}'
    there_are_inforg_comments = False

    try:
        r = requests_session.get(comment_url)  # noqa

        if not visibility_check(r, search_num):
            return False

        soup = BeautifulSoup(r.content, features='lxml')
        search_code_blocks = soup.find('div', 'post')

        # finding USERNAME
        comment_author_block = search_code_blocks.find('a', 'username')
        if not comment_author_block:
            comment_author_block = search_code_blocks.find('a', 'username-coloured')
        try:
            comment_author_nickname = comment_author_block.text
        except Exception as e:
            logging.info(f'exception for search={search_num} and comment={comment_num}')
            logging.exception(e)
            comment_author_nickname = 'unidentified_username'

        if comment_author_nickname[:6].lower() == 'инфорг' and comment_author_nickname != 'Инфорг кинологов':
            there_are_inforg_comments = True

        # finding LINK to user profile
        try:
            comment_author_link = int(''.join(filter(str.isdigit, comment_author_block['href'][36:43])))

        except Exception as e:
            logging.info(
                'Here is an exception 9 for search '
                + str(search_num)
                + ', and comment '
                + str(comment_num)
                + ' error: '
                + repr(e)
            )
            try:
                comment_author_link = int(
                    ''.join(filter(str.isdigit, search_code_blocks.find('a', 'username-coloured')['href'][36:43]))
                )
            except Exception as e2:
                logging.info('Here is an exception 10' + repr(e2))
                comment_author_link = 'unidentified_link'

        # finding the global comment id
        comment_forum_global_id = int(search_code_blocks.find('p', 'author').findNext('a')['href'][-6:])

        # finding TEXT of the comment
        comment_text_0 = search_code_blocks.find('div', 'content')
        try:
            # external_span = comment_text_0.blockquote.extract()
            comment_text_1 = comment_text_0.text
        except Exception as e:
            logging.info(f'exception for search={search_num} and comment={comment_num}')
            logging.exception(e)
            comment_text_1 = comment_text_0.text
        comment_text = ' '.join(comment_text_1.split())

        # Define exclusions (comments of Inforg with "резерв" and "рассылка билайн"
        ignore = False
        if there_are_inforg_comments:
            if comment_text.lower().endswith('резерв') or comment_text.lower().endswith('рассылка билайн'):
                ignore = True

        write_comment(
            db,
            search_num,
            comment_num,
            comment_url,
            comment_author_nickname,
            comment_author_link,
            comment_forum_global_id,
            comment_text,
            ignore,
        )

    except ConnectionResetError:
        logging.info('There is a connection error')

    return there_are_inforg_comments


def update_change_log_and_searches(db: Engine, folder_num) -> List:
    """update of SQL tables 'searches' and 'change_log' on the changes vs previous parse"""

    change_log_ids = []

    # DEBUG - function execution time counter
    func_start = datetime.now()

    with db.connect() as conn:
        curr_snapshot_list = _get_current_snapshots_list(folder_num, conn)
        prev_searches_list = _get_prev_searches(conn)

        # FIXME – temp – just to check how many lines
        print(f'TEMP – len of prev_searches_list = {len(prev_searches_list)}')
        if len(prev_searches_list) > 5000:
            logging.info('TEMP - you use too big table Searches, it should be optimized')
        # FIXME ^^^

        """1. move UPD to Change Log"""
        change_log_updates_list: list[ChangeLogLine] = []

        for snapshot_line in curr_snapshot_list:
            for searches_line in prev_searches_list:
                if snapshot_line.topic_id != searches_line.topic_id:
                    continue  # TODO we are merging two lists here. It's slow.

                changes = _detect_changes(db, snapshot_line, searches_line)
                change_log_updates_list.extend(changes)

        for line in change_log_updates_list:  # TODO
            change_log_id = _write_change_log(conn, line)
            change_log_ids.append(change_log_id)

        """2. move ADD to Change Log """
        new_topics_from_snapshot_list: list[SearchSummary] = []

        for snapshot_line in curr_snapshot_list:
            new_search_flag = 1
            for searches_line in prev_searches_list:
                if snapshot_line.topic_id == searches_line.topic_id:
                    new_search_flag = 0
                    break

            if new_search_flag == 1:
                new_topics_from_snapshot_list.append(snapshot_line)

        change_log_new_topics_list: list[ChangeLogLine] = []

        for snapshot_line in new_topics_from_snapshot_list:
            change_type_id = 0
            change_type_name = 'new_search'  # TODO enum from existing in compose_notifications

            change_log_line = ChangeLogLine(
                parsed_time=snapshot_line.parsed_time,
                topic_id=snapshot_line.topic_id,
                changed_field=change_type_name,
                new_value=snapshot_line.title,
                parameters='',
                change_type=change_type_id,
            )
            change_log_new_topics_list.append(change_log_line)

        if change_log_new_topics_list:
            for line in change_log_new_topics_list:
                change_log_id = _write_change_log(conn, line)
                change_log_ids.append(change_log_id)

        """3. ADD to Searches"""
        for line in new_topics_from_snapshot_list:
            _write_search(conn, line)

            search_num = line.topic_id
            parsed_profile_text = parse_search_profile(search_num)
            search_activities = profile_get_type_of_activity(parsed_profile_text)
            _update_search_activities(conn, search_num, search_activities)

            # Define managers of the search
            managers = profile_get_managers(parsed_profile_text)
            logging.debug(f'DBG.P.104:Managers: {managers}')
            _update_search_managers(conn, search_num, managers)

        """4 DEL UPD from Searches"""
        searches_to_delete = []

        for snapshot_line in curr_snapshot_list:
            for searches_line in prev_searches_list:
                if snapshot_line.topic_id == searches_line.topic_id:
                    if (
                        snapshot_line.status != searches_line.status
                        or snapshot_line.title != searches_line.title
                        or snapshot_line.num_of_replies != searches_line.num_of_replies
                    ):
                        searches_to_delete.append(snapshot_line)

        for line in searches_to_delete:
            # TODO mass deletion
            _delete_search(conn, line.topic_id)

        """5. UPD added to Searches"""
        curr_searches_list = _get_current_searches(conn)

        new_topics_from_snapshot_list = []

        for snapshot_line in curr_snapshot_list:
            new_search_flag = 1
            for searches_line in curr_searches_list:
                if snapshot_line.topic_id == searches_line.topic_id:
                    new_search_flag = 0
                    break
            if new_search_flag == 1:
                new_topics_from_snapshot_list.append(snapshot_line)
        if new_topics_from_snapshot_list:
            for line in new_topics_from_snapshot_list:
                _write_search(conn, line)

    # DEBUG - function execution time counter
    func_finish = datetime.now()
    func_execution_time_ms = func_finish - func_start
    logging.info(f'DBG.P.5.process_delta() exec time: {func_execution_time_ms}')

    return change_log_ids


def _detect_changes(db: Engine, snapshot_line: SearchSummary, searches_line: SearchSummary) -> list[ChangeLogLine]:
    change_log_updates_list: list[ChangeLogLine] = []
    there_are_inforg_comments = False
    if snapshot_line.status != searches_line.status:
        change_log_line = ChangeLogLine(
            parsed_time=snapshot_line.parsed_time,
            topic_id=snapshot_line.topic_id,
            changed_field='status_change',
            new_value=snapshot_line.status,
            parameters='',
            change_type=ChangeType.topic_status_change,
        )

        change_log_updates_list.append(change_log_line)

    if snapshot_line.title != searches_line.title:
        change_log_line = ChangeLogLine(
            parsed_time=snapshot_line.parsed_time,
            topic_id=snapshot_line.topic_id,
            changed_field='title_change',
            new_value=snapshot_line.title,
            parameters='',
            change_type=ChangeType.topic_title_change,
        )

        change_log_updates_list.append(change_log_line)

    if snapshot_line.num_of_replies > searches_line.num_of_replies:
        change_log_line = ChangeLogLine(
            parsed_time=snapshot_line.parsed_time,
            topic_id=snapshot_line.topic_id,
            changed_field='replies_num_change',
            new_value=snapshot_line.num_of_replies,
            parameters='',
            change_type=ChangeType.topic_comment_new,
        )

        change_log_updates_list.append(change_log_line)

        for k in range(snapshot_line.num_of_replies - searches_line.num_of_replies):
            flag_if_comment_was_from_inforg = parse_and_write_one_comment(
                db, snapshot_line.topic_id, searches_line.num_of_replies + 1 + k
            )  # TODO could extract out of here?
            if flag_if_comment_was_from_inforg:
                there_are_inforg_comments = True

        if there_are_inforg_comments:
            change_log_line = ChangeLogLine(
                parsed_time=snapshot_line.parsed_time,
                topic_id=snapshot_line.topic_id,
                changed_field='inforg_replies',
                new_value=snapshot_line.num_of_replies,
                parameters='',
                change_type=ChangeType.topic_inforg_comment_new,
            )

            change_log_updates_list.append(change_log_line)
    return change_log_updates_list


def update_checker(current_hash: str, folder_num: int) -> bool:
    """compare prev snapshot and freshly-parsed snapshot, returns NO or YES and Previous hash"""

    folder_hash_storage = CloudStorage()

    previous_hash = folder_hash_storage.read_folder_hash(folder_num)
    if current_hash == previous_hash:
        return False

    # update hash in Storage
    folder_hash_storage.write_folder_hash(current_hash, folder_num)
    logging.info(f'folder = {folder_num}, hash is updated, prev snapshot as string = {previous_hash}')

    return True


def process_one_folder(db: Engine, folder_to_parse: str) -> Tuple[bool, List]:
    """process one forum folder: check for updates, upload them into cloud sql"""

    change_log_ids = []

    # parse a new version of summary page from the chosen folder
    titles_and_num_of_replies, new_folder_summary = parse_one_folder(db, folder_to_parse)

    update_trigger = False

    if not new_folder_summary:
        return False, []

    # transform the current snapshot into the string to be able to compare it: string vs string
    curr_snapshot_as_one_dimensional_list = [y for x in titles_and_num_of_replies for y in x]
    curr_snapshot_as_string = ','.join(map(str, curr_snapshot_as_one_dimensional_list))

    # get the prev snapshot as string from cloud storage & get the trigger if there are updates at all
    update_trigger = update_checker(curr_snapshot_as_string, folder_to_parse)

    if not update_trigger:
        return False, []

    rewrite_snapshot_in_sql(db, folder_to_parse, new_folder_summary)

    logging.info(f'starting updating change_log and searches tables for folder {folder_to_parse}')

    change_log_ids = update_change_log_and_searches(db, folder_to_parse)
    update_coordinates(db, new_folder_summary)

    return True, change_log_ids


def main(event, context) -> None:  # noqa
    """main function triggered by pub/sub"""

    requests_session = get_requests_session()

    function_id = generate_random_function_id()
    folders_list = []

    analytics_func_start = datetime.now()
    requests_session = requests.Session()

    message_from_pubsub = process_pubsub_message_v3(event)
    list_from_pubsub = ast.literal_eval(message_from_pubsub) if message_from_pubsub else None
    logging.info(f'received message from pub/sub: {message_from_pubsub}')

    db = sql_connect()
    list_of_ignored_folders = get_the_list_of_ignored_folders(db)

    if list_from_pubsub:
        folders_list = [int(line[0]) for line in list_from_pubsub if int(line[0]) not in list_of_ignored_folders]
        logging.info(f'list of folders, received from pubsub but filtered by ignored folders: {folders_list}')

    if not folders_list:
        notify_admin(f'NB! [Ide_topics] resulted in empty folders list. Initial, but filtered {list_from_pubsub}')
        folders_list = [276, 41]

    list_of_folders_with_updates = []
    change_log_ids = []

    if folders_list:
        for folder in folders_list:
            logging.info(f'start checking if folder {folder} has any updates')

            update_trigger, one_folder_change_log_ids = process_one_folder(db, folder)

            if update_trigger:
                list_of_folders_with_updates.append(folder)
                change_log_ids += one_folder_change_log_ids

    logging.info(f"Here's a list of folders with updates: {list_of_folders_with_updates}")
    logging.info(f"Here's a list of change_log ids created: {change_log_ids}")

    if list_of_folders_with_updates:
        save_function_into_register(db, context, analytics_func_start, function_id, change_log_ids)

        message_for_pubsub = {'triggered_by_func_id': function_id, 'text': "let's compose notifications"}
        publish_to_pubsub(Topics.topic_for_notification, message_for_pubsub)

    requests_session.close()
    db.dispose()
