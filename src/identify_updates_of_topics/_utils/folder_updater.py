import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import storage
from google.cloud.storage.blob import Blob

from _dependencies.commons import ChangeType, TopicType
from _dependencies.misc import make_api_call, notify_admin
from _dependencies.recognition_schema import RecognitionResult, RecognitionTopicType

from .database import DBClient
from .external_api import (
    get_coordinates_from_address_by_osm,
    get_coordinates_from_address_by_yandex,
)
from .forum import ForumClient
from .parse import (
    parse_address_from_title,
    profile_get_managers,
    profile_get_type_of_activity,
)
from .topics_commons import (
    ChangeLogLine,
    CoordType,
    ForumSearchItem,
    SearchSummary,
)


class CloudStorage:
    BUCKET_NAME = 'bucket_for_snapshot_storage'

    def read_folder_hash(self, folder_num: int) -> str | None:
        try:
            blob = self._set_cloud_storage(folder_num)
            contents_as_bytes = blob.download_as_string()
            contents = str(contents_as_bytes, 'utf-8')
        except:  # noqa
            contents = None

        return contents

    def write_folder_hash(self, data: Any, folder_num: int) -> None:
        blob = self._set_cloud_storage(folder_num)
        blob.upload_from_string(data)

    def _set_cloud_storage(self, folder_num: int) -> Blob:
        """sets the basic parameters for connection to txt file in cloud storage, which stores searches snapshots"""

        storage_client = storage.Client()  # TODO move to class initialization
        bucket = storage_client.get_bucket(self.BUCKET_NAME)

        blob_name = f'{folder_num}.txt'
        return bucket.blob(blob_name)


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
    def __init__(self, db_client: DBClient, forum_client: ForumClient, folder_num: int) -> None:
        self.folder_num = folder_num
        self.forum = forum_client
        self.db = db_client

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

        logging.info(f'starting updating change_log and searches tables for folder {self.folder_num}')

        change_log_ids = self._update_change_log_and_searches(new_folder_summary)
        self._update_coordinates(new_folder_summary)

        return True, change_log_ids

    def _parse_one_folder(self) -> tuple[list, list[SearchSummary]]:
        """parse forum folder with searches' summaries"""

        folder_summary: list[SearchSummary] = []
        current_datetime = datetime.now()

        folder_content_items = self.forum.get_folder_searches(self.folder_num)
        for forum_search_item in folder_content_items:
            try:
                self._parse_one_search(current_datetime, folder_summary, forum_search_item)

            except Exception as e:
                logging.exception(f'TEMP - THIS BIG ERROR HAPPENED, {forum_search_item=}')
                notify_admin(f'TEMP - THIS BIG ERROR HAPPENED, {forum_search_item=}')

        titles_and_num_of_replies = [[x.title, x.num_of_replies] for x in folder_summary]
        return titles_and_num_of_replies, folder_summary

    def _parse_one_search(
        self,
        current_datetime: datetime,
        folder_summary: list[SearchSummary],
        forum_search_item: ForumSearchItem,
    ) -> None:
        topic_type_dict = {
            RecognitionTopicType.search: TopicType.search_regular,
            RecognitionTopicType.search_reverse: TopicType.search_reverse,
            RecognitionTopicType.search_patrol: TopicType.search_patrol,
            RecognitionTopicType.search_training: TopicType.search_training,
            RecognitionTopicType.event: TopicType.event,
            # TODO RecognitionTopicType.info ?
            # TODO move mapping near enum definition
        }

        data = {'title': forum_search_item.title}
        title_reco_response = make_api_call('title_recognize', data)

        if title_reco_response and 'status' in title_reco_response.keys() and title_reco_response['status'] == 'ok':
            title_reco_dict = RecognitionResult.model_validate(title_reco_response['recognition'])
            # TODO validate whole response
        else:
            return

        logging.debug(f'{title_reco_dict=}')

        # FIXME – 06.11.2023 – work to delete function "define_family_name_from_search_title_new"
        if title_reco_dict.topic_type == RecognitionTopicType.event:
            person_fam_name = None
        else:
            person_fam_name = title_reco_dict.persons.total_name if title_reco_dict.persons else 'БВП'

        search_summary_object = SearchSummary(
            parsed_time=current_datetime,
            topic_id=forum_search_item.search_id,
            title=forum_search_item.title,
            start_time=forum_search_item.start_datetime,
            num_of_replies=forum_search_item.replies_count,
            name=person_fam_name,
            folder_id=self.folder_num,
            topic_type=title_reco_dict.topic_type,
            topic_type_id=topic_type_dict[title_reco_dict.topic_type],
            new_status=title_reco_dict.status,
            status=title_reco_dict.status,
        )

        if title_reco_dict.persons:
            search_summary_object.display_name = title_reco_dict.persons.total_display_name
            search_summary_object.age = title_reco_dict.persons.age_min
            # Due to the field "age" in searches which is integer, so we cannot indicate a range
            search_summary_object.age_min = title_reco_dict.persons.age_min
            search_summary_object.age_max = title_reco_dict.persons.age_max

        if title_reco_dict.locations:
            list_of_location_cities = [loc.address for loc in title_reco_dict.locations]
            list_of_location_coords = []
            for location_city in list_of_location_cities:
                city_lat, city_lon = self._get_coordinates_by_address(location_city)
                if city_lat and city_lon:
                    list_of_location_coords.append([city_lat, city_lon])
            search_summary_object.locations = list_of_location_coords

        folder_summary.append(search_summary_object)

    def _update_change_log_and_searches(self, new_folder_summary: list[SearchSummary]) -> list[int]:
        """update of SQL tables 'searches' and 'change_log' on the changes vs previous parse"""
        self.db.rewrite_snapshot_in_sql(self.folder_num, new_folder_summary)
        # TODO maybe we dont need snapshots at all.

        # DEBUG - function execution time counter
        func_start = datetime.now()

        curr_snapshot_list = self.db.get_current_snapshots_list(self.folder_num)
        # TODO maybe we dont need snapshots at all. new_folder_summary is enough.
        prev_searches_list = self.db.get_searches()

        logging.debug(f'TEMP – len of prev_searches_list = {len(prev_searches_list)}')
        if len(prev_searches_list) > 5000:
            logging.warning('TEMP - you use too big table Searches, it should be optimized')

        change_log_ids = self._write_updated_searches_to_changelog(curr_snapshot_list, prev_searches_list)
        new_change_log_ids = self._write_new_searches_to_changelog(curr_snapshot_list, prev_searches_list)
        change_log_ids.extend(new_change_log_ids)

        self._update_changed_searches(curr_snapshot_list, prev_searches_list)

        # DEBUG - function execution time counter
        func_finish = datetime.now()
        func_execution_time_ms = func_finish - func_start
        logging.info(f'DBG.P.5.process_delta() exec time: {func_execution_time_ms}')

        return change_log_ids

    def _update_changed_searches(
        self, curr_snapshot_list: list[SearchSummary], prev_searches_list: list[SearchSummary]
    ) -> None:
        for snapshot in curr_snapshot_list:
            for search in prev_searches_list:
                if snapshot.topic_id != search.topic_id:
                    continue
                if (
                    snapshot.status != search.status
                    or snapshot.title != search.title
                    or snapshot.num_of_replies != search.num_of_replies
                ):
                    self.db.delete_search(search.topic_id)
                    self.db.write_search(snapshot)

    def _write_new_searches_to_changelog(
        self, curr_snapshot_list: list[SearchSummary], prev_searches_list: list[SearchSummary]
    ) -> list[int]:
        prev_searches_topic_ids = set([search.topic_id for search in prev_searches_list])

        new_topics = [x for x in curr_snapshot_list if x.topic_id not in prev_searches_topic_ids]
        change_log_ids: list[int] = []

        for search_summary_line in new_topics:
            search_num = search_summary_line.topic_id
            parsed_profile_text = self.forum.parse_search_profile(search_num)
            search_activities = profile_get_type_of_activity(parsed_profile_text)
            managers = profile_get_managers(parsed_profile_text)

            self.db.write_search(search_summary_line)
            self.db.update_search_activities(search_num, search_activities)
            self.db.update_search_managers(search_num, managers)

            line = ChangeLogLine(
                parsed_time=search_summary_line.parsed_time,
                topic_id=search_summary_line.topic_id,
                changed_field='new_search',
                new_value=search_summary_line.title,
                parameters='',
                change_type=ChangeType.topic_new,
            )
            # TODO can we collect all ChangeLogLine creation on one place?

            change_log_id = self.db.write_change_log(line)
            change_log_ids.append(change_log_id)

        return change_log_ids

    def _write_updated_searches_to_changelog(
        self, curr_snapshot_list: list[SearchSummary], prev_searches_list: list[SearchSummary]
    ) -> list[int]:
        change_log_ids: list[int] = []
        change_log_updates_list: list[ChangeLogLine] = []

        for snapshot in curr_snapshot_list:
            for search in prev_searches_list:
                if snapshot.topic_id != search.topic_id:
                    continue  # TODO we are merging two lists here. It's slow.

                # take the search matched with the snapshot by topic_id

                there_are_inforg_comments = self._parse_comments_and_detect_inforg_comments(snapshot, search)
                changes = self._detect_changes(snapshot, search, there_are_inforg_comments)
                change_log_updates_list.extend(changes)

        for line in change_log_updates_list:  # TODO
            change_log_id = self.db.write_change_log(line)
            change_log_ids.append(change_log_id)

        return change_log_ids

    def _parse_comments_and_detect_inforg_comments(
        self, snapshot_line: SearchSummary, searches_line: SearchSummary
    ) -> bool:
        if snapshot_line.num_of_replies <= searches_line.num_of_replies:
            return False

        there_are_inforg_comments = False
        for comment_number in range(searches_line.num_of_replies + 1, snapshot_line.num_of_replies + 1):
            comment_data = self.forum.get_comment_data(snapshot_line.topic_id, comment_number)
            if not comment_data:
                continue

            self.db.write_comment(comment_data)

            there_are_inforg_comments = there_are_inforg_comments or comment_data.inforg_comment_present

        return there_are_inforg_comments

    def _update_coordinates(self, list_of_search_objects: list[SearchSummary]) -> None:
        """Record search coordinates to PSQL"""

        for search in list_of_search_objects:
            search_id = search.topic_id
            search_status = search.new_status

            if search_status not in {'Ищем', 'СТОП'}:
                continue

            logging.info(f'search coordinates should be saved for {search_id=}')
            coords = self._parse_coordinates_of_search(search_id)

            self.db.update_coordinates_in_db(search_id, coords[0], coords[1], coords[2])

        return None

    def _parse_coordinates_of_search(self, search_num: int) -> tuple[float, float, CoordType]:
        """finds coordinates of the search"""

        # DEBUG - function execution time counter
        func_start = datetime.now()

        lat, lon, coord_type, title = self.forum.parse_coordinates_of_search(search_num)

        # FOURTH CASE = COORDINATES FROM ADDRESS
        if not lat:
            try:
                address = parse_address_from_title(title)
                if address:
                    self.db.save_place_in_psql(address, search_num)
                    lat, lon = self._get_coordinates_by_address(address)
                    if lat and lon:
                        coord_type = CoordType.type_4_from_title
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
        # there_are_inforg_comments = False
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

    def _get_coordinates_by_address(self, address: str) -> tuple[float, float] | tuple[None, None]:
        """convert address string into a pair of coordinates"""

        try:
            # check if this address was already geolocated and saved to psql
            saved_status, lat, lon, saved_geocoder = self.db.get_geolocation_form_psql(address)

            if lat and lon:
                return lat, lon

            elif saved_status == 'fail' and saved_geocoder == 'yandex':
                return None, None

            elif not saved_status:
                # when there's no saved record
                self._rate_limit_for_api(geocoder='osm')
                lat, lon = get_coordinates_from_address_by_osm(address)
                self.db.save_last_api_call_time_to_psql(geocoder='osm')

                if lat and lon:
                    saved_status = 'ok'
                    self.db.save_geolocation_in_psql(address, saved_status, lat, lon, 'osm')
                else:
                    saved_status = 'fail'

            if saved_status == 'fail' and (saved_geocoder == 'osm' or not saved_geocoder):
                # then we need to geocode with yandex
                self._rate_limit_for_api(geocoder='yandex')
                lat, lon = get_coordinates_from_address_by_yandex(address)
                self.db.save_last_api_call_time_to_psql(geocoder='yandex')

                saved_status = 'ok' if lat and lon else 'fail'
                self.db.save_geolocation_in_psql(address, saved_status, lat, lon, 'yandex')

            return lat, lon

        except Exception as e:
            logging.exception('TEMP - LOC - New getting coordinates from title failed')
            notify_admin('ERROR: major geocoding script failed')

        return None, None

    def _rate_limit_for_api(self, geocoder: str) -> None:
        """sleeps certain time if api calls are too frequent"""

        # check that next request won't be in less a SECOND from previous
        prev_api_call_time = self.db.get_last_api_call_time_from_psql(geocoder)  # TODO

        if not prev_api_call_time:
            return

        if geocoder == 'yandex':
            return

        now_utc = datetime.now(timezone.utc)
        time_delta_bw_now_and_next_request = prev_api_call_time - now_utc + timedelta(seconds=1)

        logging.debug(f'{prev_api_call_time=}')
        logging.debug(f'{now_utc=}')
        logging.debug(f'{time_delta_bw_now_and_next_request=}')

        if time_delta_bw_now_and_next_request.total_seconds() > 0:
            time.sleep(time_delta_bw_now_and_next_request.total_seconds())
            logging.debug(f'rate limit for {geocoder}: sleep {time_delta_bw_now_and_next_request.total_seconds()}')
            notify_admin(f'rate limit for {geocoder}: sleep {time_delta_bw_now_and_next_request.total_seconds()}')
