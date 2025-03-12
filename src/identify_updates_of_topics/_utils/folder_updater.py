import logging
from datetime import datetime
from typing import Any

import requests
from google.cloud import storage
from google.cloud.storage.blob import Blob
from sqlalchemy.engine.base import Engine

from _dependencies.commons import ChangeType, TopicType
from _dependencies.misc import make_api_call, notify_admin
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
    rewrite_snapshot_in_sql,
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
from identify_updates_of_topics._utils.forum import ForumClient
from identify_updates_of_topics._utils.parse import (
    parse_address_from_title,
    profile_get_managers,
    profile_get_type_of_activity,
)
from identify_updates_of_topics._utils.topics_commons import ChangeLogLine, SearchSummary


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


class FolderUpdater:
    # TODO split: FolderUpdater and maybe SearchUpdater
    def __init__(self, db: Engine, folder_num: int) -> None:
        self.db = db
        self.folder_num = folder_num

    def run(self) -> tuple[bool, list[int]]:
        """process one forum folder: check for updates, upload them into cloud sql"""

        change_log_ids = []

        # parse a new version of summary page from the chosen folder
        titles_and_num_of_replies, new_folder_summary = self._parse_one_folder()

        update_trigger = False

        if not new_folder_summary:
            return False, []

        # transform the current snapshot into the string to be able to compare it: string vs string
        curr_snapshot_as_one_dimensional_list = [y for x in titles_and_num_of_replies for y in x]
        curr_snapshot_as_string = ','.join(map(str, curr_snapshot_as_one_dimensional_list))

        # get the prev snapshot as string from cloud storage & get the trigger if there are updates at all
        update_trigger = update_checker(curr_snapshot_as_string, self.folder_num)

        if not update_trigger:
            return False, []

        rewrite_snapshot_in_sql(self.db, self.folder_num, new_folder_summary)

        logging.info(f'starting updating change_log and searches tables for folder {self.folder_num}')

        change_log_ids = self._update_change_log_and_searches()
        self.update_coordinates(new_folder_summary)

        return True, change_log_ids

    def _parse_one_folder(self) -> tuple[list, list[SearchSummary]]:
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
        folder_content_items = forum_client.get_folder_searches(self.folder_num)
        try:
            for forum_search_item in folder_content_items:
                data = {'title': forum_search_item.title}
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
                            title=forum_search_item.title,
                            start_time=forum_search_item.start_datetime,
                            num_of_replies=forum_search_item.replies_count,
                            name=person_fam_name,
                            folder_id=self.folder_num,
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
                                city_lat, city_lon = self.get_coordinates_by_address(location_city)
                                if city_lat and city_lon:
                                    list_of_location_coords.append([city_lat, city_lon])
                            search_summary_object.locations = list_of_location_coords

                        folder_summary.append(search_summary_object)

                        search_summary = [
                            current_datetime,
                            forum_search_item.search_id,
                            search_summary_object.status,
                            forum_search_item.title,
                            '',
                            forum_search_item.start_datetime,
                            forum_search_item.replies_count,
                            search_summary_object.age_min,
                            person_fam_name,
                            self.folder_num,
                        ]
                        topics_summary_in_folder.append(search_summary)

                        parsed_wo_date = [forum_search_item.title, forum_search_item.replies_count]
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

        logging.info(f'folder = {self.folder_num}, old_topics_summary = {topics_summary_in_folder}')

        return titles_and_num_of_replies, folder_summary

    def _update_change_log_and_searches(self) -> list[int]:
        """update of SQL tables 'searches' and 'change_log' on the changes vs previous parse"""

        change_log_ids = []

        # DEBUG - function execution time counter
        func_start = datetime.now()

        with self.db.connect() as conn:
            curr_snapshot_list = _get_current_snapshots_list(self.folder_num, conn)
            prev_searches_list = _get_prev_searches(conn)

            print(f'TEMP – len of prev_searches_list = {len(prev_searches_list)}')
            if len(prev_searches_list) > 5000:
                logging.warning('TEMP - you use too big table Searches, it should be optimized')

            """1. move UPD to Change Log"""
            change_log_updates_list: list[ChangeLogLine] = []

            for snapshot_line in curr_snapshot_list:
                for searches_line in prev_searches_list:
                    if snapshot_line.topic_id != searches_line.topic_id:
                        continue  # TODO we are merging two lists here. It's slow.

                    there_are_inforg_comments = self._parse_comments_and_detect_inforg_comments(
                        snapshot_line, searches_line
                    )
                    changes = self._detect_changes(snapshot_line, searches_line, there_are_inforg_comments)
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
                change_type_id = ChangeType.topic_new
                change_type_name = 'new_search'

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
                parsed_profile_text = ForumClient().parse_search_profile(search_num)
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

            new_searches: list[SearchSummary] = []

            for snapshot_line in curr_snapshot_list:
                new_search_flag = 1
                for searches_line in curr_searches_list:
                    if snapshot_line.topic_id == searches_line.topic_id:
                        new_search_flag = 0
                        break  # search already exists
                if new_search_flag == 1:
                    new_searches.append(snapshot_line)

            for line in new_searches:
                _write_search(conn, line)

        # DEBUG - function execution time counter
        func_finish = datetime.now()
        func_execution_time_ms = func_finish - func_start
        logging.info(f'DBG.P.5.process_delta() exec time: {func_execution_time_ms}')

        return change_log_ids

    def _parse_comments_and_detect_inforg_comments(
        self, snapshot_line: SearchSummary, searches_line: SearchSummary
    ) -> bool:
        if snapshot_line.num_of_replies <= searches_line.num_of_replies:
            return False

        there_are_inforg_comments = False
        for k in range(snapshot_line.num_of_replies - searches_line.num_of_replies):
            flag_if_comment_was_from_inforg = self.parse_and_write_one_comment(
                snapshot_line.topic_id, searches_line.num_of_replies + 1 + k
            )
            if flag_if_comment_was_from_inforg:
                there_are_inforg_comments = True

        return there_are_inforg_comments

    def parse_and_write_one_comment(self, search_num, comment_num: int) -> bool:
        """parse all details on a specific comment in topic (by sequence number)"""

        try:
            forum_client = ForumClient()
            comment_data = forum_client.get_comment_data(search_num, comment_num)
            write_comment(
                self.db,
                comment_data.search_num,
                comment_data.comment_num,
                comment_data.comment_url,
                comment_data.comment_author_nickname,
                comment_data.comment_author_link,
                comment_data.comment_forum_global_id,
                comment_data.comment_text,
                comment_data.ignore,
            )

        except ConnectionResetError:
            logging.info('There is a connection error')

        return comment_data.inforg_comment_present

    def update_coordinates(self, list_of_search_objects: list[SearchSummary]) -> None:
        """Record search coordinates to PSQL"""

        for search in list_of_search_objects:
            search_id = search.topic_id
            search_status = search.new_status

            if search_status not in {'Ищем', 'СТОП'}:
                continue

            logging.info(f'search coordinates should be saved for {search_id=}')
            coords = self.parse_coordinates_of_search(search_id)

            update_coordinates_in_db(self.db, search_id, coords)

        return None

    def parse_coordinates_of_search(self, search_num) -> tuple[float, float, str]:
        """finds coordinates of the search"""

        # DEBUG - function execution time counter
        func_start = datetime.now()

        lat, lon, coord_type, title = ForumClient().parse_coordinates_of_search(search_num)

        # FOURTH CASE = COORDINATES FROM ADDRESS
        if lat == 0:
            try:
                address = parse_address_from_title(title)
                if address:
                    save_place_in_psql(self.db, address, search_num)
                    lat, lon = self.get_coordinates_by_address(address)
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

    def _detect_changes(
        self, snapshot_line: SearchSummary, searches_line: SearchSummary, there_are_inforg_comments: bool
    ) -> list[ChangeLogLine]:
        change_log_updates_list: list[ChangeLogLine] = []
        there_are_inforg_comments = False
        if snapshot_line.status != searches_line.status:
            change_log_updates_list.append(
                ChangeLogLine(
                    parsed_time=snapshot_line.parsed_time,
                    topic_id=snapshot_line.topic_id,
                    changed_field='status_change',
                    new_value=snapshot_line.status,
                    parameters='',
                    change_type=ChangeType.topic_status_change,
                )
            )

        if snapshot_line.title != searches_line.title:
            change_log_updates_list.append(
                ChangeLogLine(
                    parsed_time=snapshot_line.parsed_time,
                    topic_id=snapshot_line.topic_id,
                    changed_field='title_change',
                    new_value=snapshot_line.title,
                    parameters='',
                    change_type=ChangeType.topic_title_change,
                )
            )

        if snapshot_line.num_of_replies > searches_line.num_of_replies:
            change_log_updates_list.append(
                ChangeLogLine(
                    parsed_time=snapshot_line.parsed_time,
                    topic_id=snapshot_line.topic_id,
                    changed_field='replies_num_change',
                    new_value=snapshot_line.num_of_replies,
                    parameters='',
                    change_type=ChangeType.topic_comment_new,
                )
            )

            if there_are_inforg_comments:
                change_log_updates_list.append(
                    ChangeLogLine(
                        parsed_time=snapshot_line.parsed_time,
                        topic_id=snapshot_line.topic_id,
                        changed_field='inforg_replies',
                        new_value=snapshot_line.num_of_replies,
                        parameters='',
                        change_type=ChangeType.topic_inforg_comment_new,
                    )
                )
        return change_log_updates_list

    def get_coordinates_by_address(self, address: str) -> tuple[float, float] | tuple[None, None]:
        """convert address string into a pair of coordinates"""

        try:
            # check if this address was already geolocated and saved to psql
            saved_status, lat, lon, saved_geocoder = get_geolocation_form_psql(self.db, address)

            if lat and lon:
                return lat, lon

            elif saved_status == 'fail' and saved_geocoder == 'yandex':
                return None, None

            elif not saved_status:
                # when there's no saved record
                rate_limit_for_api(db=self.db, geocoder='osm')
                lat, lon = get_coordinates_from_address_by_osm(address)
                api_call_time_saved = save_last_api_call_time_to_psql(db=self.db, geocoder='osm')
                logging.info(f'{api_call_time_saved=}')

                if lat and lon:
                    saved_status = 'ok'
                    save_geolocation_in_psql(self.db, address, saved_status, lat, lon, 'osm')
                else:
                    saved_status = 'fail'

            if saved_status == 'fail' and (saved_geocoder == 'osm' or not saved_geocoder):
                # then we need to geocode with yandex
                rate_limit_for_api(db=self.db, geocoder='yandex')
                lat, lon = get_coordinates_from_address_by_yandex(address)
                api_call_time_saved = save_last_api_call_time_to_psql(db=self.db, geocoder='yandex')
                logging.info(f'{api_call_time_saved=}')

                if lat and lon:
                    saved_status = 'ok'
                else:
                    saved_status = 'fail'
                save_geolocation_in_psql(self.db, address, saved_status, lat, lon, 'yandex')

            return lat, lon

        except Exception as e:
            logging.exception('TEMP - LOC - New getting coordinates from title failed')
            notify_admin('ERROR: major geocoding script failed')

        return None, None
