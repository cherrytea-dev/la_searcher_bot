import ast
import datetime
import logging
from functools import lru_cache
from typing import Any, no_type_check

import requests
from bs4 import BeautifulSoup, SoupStrainer, Tag
from google.cloud import storage
from google.cloud.functions.context import Context
from google.cloud.storage.blob import Blob
from retry.api import retry_call

from _dependencies.commons import Topics, publish_to_pubsub, setup_google_logging

setup_google_logging()

DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S+00:00'


@lru_cache
def get_session() -> requests.Session:
    return requests.Session()


class CloudStorage:
    ROOT_MODIFIED_TIMES_KEY = 'root_modified_times'

    def read_foder_root_modified_times_dict(self) -> dict[str, str]:
        try:
            times_dict = self._read_snapshot(self.ROOT_MODIFIED_TIMES_KEY)
            return ast.literal_eval(times_dict) if times_dict else {}
        except Exception as e:
            logging.info(f'Failed to read snapshot from storage: {str(e)}')
            return {}

    def write_foder_root_modified_times_dict(self, data: Any) -> None:
        return self._write_snapshot(data, str(self.ROOT_MODIFIED_TIMES_KEY))

    def _read_snapshot(self, snapshot_name: str) -> str | None:
        """reads previous searches snapshot from txt file in cloud storage"""

        try:
            blob = self._set_cloud_storage(snapshot_name)
            contents_as_bytes = blob.download_as_string()
            contents: str | None = str(contents_as_bytes, 'utf-8')
            if contents == 'None':
                contents = None
        except:  # noqa
            contents = None
        return contents

    def _write_snapshot(self, what_to_write: Any, snapshot_name: str) -> None:
        """writes current snapshot to txt file in cloud storage"""

        blob = self._set_cloud_storage(snapshot_name)
        blob.upload_from_string(str(what_to_write), content_type='text/plain')

    def _set_cloud_storage(self, folder_num: str) -> Blob:
        """sets the basic parameters for connection to txt file in cloud storage, which stores searches snapshots"""
        bucket_name = 'bucket_for_folders_snapshots'
        blob_name = str(folder_num) + '.txt'

        storage_client = storage.Client()
        bucket = storage_client.get_bucket(bucket_name)
        blob = bucket.blob(blob_name)

        return blob


class FolderUpdateChecker:
    def __init__(self) -> None:
        self.url = 'https://lizaalert.org/forum/index.php'
        self.useless_folders = {84, 113, 112, 270, 86, 87, 88, 165, 365, 89, 172, 91, 90}

    def check_updates_in_folder_with_folders(self) -> list[list]:
        """Check if there are changes in folder that contain other folders"""
        page_summary = []

        soup = self._fetch_and_parse_forum_page()
        search_code_blocks = soup.find_all('div', {'class': 'forabg'})
        if search_code_blocks:
            search_code_blocks = self._filter_search_code_blocks(search_code_blocks)  # type:ignore[assignment]

            for block in search_code_blocks:
                folders = block.find_all('li', {'class': 'row'})
                for folder in folders:
                    folder_num, folder_time_str, folder_time = self._extract_folder_info(folder)

                    if folder_num in self.useless_folders:
                        continue
                    page_summary.append([folder_num, folder_time_str, folder_time])

        return page_summary

    def _fetch_and_parse_forum_page(self) -> BeautifulSoup:
        r = retry_call(get_session().get, fkwargs={'url': self.url, 'timeout': 20}, tries=5)
        only_tag = SoupStrainer('div', {'class': 'forabg'})
        return BeautifulSoup(r.content, features='lxml', parse_only=only_tag)

    def _filter_search_code_blocks(self, search_code_blocks: list[Tag]) -> list[Tag]:
        temp_block = search_code_blocks[-2]
        search_code_blocks = search_code_blocks[0:3]
        search_code_blocks.append(temp_block)
        return search_code_blocks

    def _extract_folder_info(self, folder: Tag) -> tuple[int, str, datetime.datetime]:
        folder_num = self._extract_folder_num(folder)
        folder_time_str, folder_time = self._extract_folder_time(folder)
        return folder_num, folder_time_str, folder_time

    def _extract_folder_num(self, folder: Tag) -> int:
        folder_num_str = str(folder.find('a', {'class': 'forumtitle'})['href'])  # type:ignore[index]
        start_symb_to_del = folder_num_str.find('&sid=')
        if start_symb_to_del != -1:
            return int(folder_num_str[18:start_symb_to_del])  # type:ignore[arg-type]
        return int(folder_num_str[18:])

    def _extract_folder_time(self, folder: Tag) -> tuple[str, datetime.datetime]:
        try:
            folder_time_str = str(folder.find('time')['datetime'])  # type:ignore[index]
            folder_time = datetime.datetime.strptime(folder_time_str, DATETIME_FORMAT)
        except Exception:  # noqa
            folder_time_str = str(datetime.datetime(2023, 1, 1, 0, 0, 0))
            folder_time = datetime.datetime(2023, 1, 1, 0, 0, 0)
        return folder_time_str, folder_time


def time_delta(now: datetime.datetime, time: datetime.datetime) -> int:
    """provides a difference in minutes for 2 timestamps"""
    time_diff = now - time
    time_diff_in_min = (time_diff.days * 24 * 60) + (time_diff.seconds // 60)
    return time_diff_in_min


def get_the_list_folders_to_update(list_of_folders_and_times: list[list]) -> list:
    """get the list of updated folders that were updated recently"""
    storage = CloudStorage()
    update_times = storage.read_foder_root_modified_times_dict()
    updated_folders = []

    for f_num, f_time_str, f_time in list_of_folders_and_times:
        saved_update_time = update_times.get(f_num, datetime.datetime.min)
        if f_time_str != saved_update_time:
            updated_folders.append([f_num, f_time_str])
            update_times[f_num] = f_time_str

    storage.write_foder_root_modified_times_dict(update_times)
    return updated_folders


def main(event: dict[str, Any], context: Context) -> None:
    """main function that starts first"""
    logging.info('START')
    now = datetime.datetime.now()

    folder_checker = FolderUpdateChecker()
    list_of_folders_and_times = folder_checker.check_updates_in_folder_with_folders()

    last_update_time = max(x[2] for x in list_of_folders_and_times)
    time_diff_in_min = time_delta(now, last_update_time)
    logging.info(f'{str(time_diff_in_min)} minute(s) ago forum was updated')

    list_of_updated_folders = get_the_list_folders_to_update(list_of_folders_and_times)
    logging.info(f'Folders with new info: {str(list_of_updated_folders)}')

    list_for_pubsub = [[line[0], line[1]] for line in list_of_updated_folders]
    if list_for_pubsub:
        publish_to_pubsub(Topics.topic_update_identified, str(list_for_pubsub))
