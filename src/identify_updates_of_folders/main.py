"""Parses the folder-tree on the forum, checking the last update time. Collects the list of leaf-level folders
which contain updates – and makes a pub/sub call for other script to parse content of these folders"""

import ast
import logging
from dataclasses import dataclass
from typing import Any, Optional, no_type_check

import requests
from bs4 import BeautifulSoup, SoupStrainer, Tag
from google.cloud import storage
from google.cloud.functions.context import Context
from google.cloud.storage.blob import Blob

from _dependencies.commons import Topics, publish_to_pubsub, setup_google_logging
from _dependencies.misc import process_pubsub_message

setup_google_logging()


@dataclass
class FolderForDecompose:
    mother_folder_num: str
    mother_folder_name: str | None = None


@dataclass
class Subfolder:
    folder_num: int
    change_time_str: str

    def __repr__(self) -> str:
        """for compatibility with current cloud storage"""
        return str([self.folder_num, self.change_time_str])


@dataclass
class Search:
    title: str
    change_time_str: str

    def __repr__(self) -> str:
        """for compatibility with current cloud storage"""
        return str([self.title, self.change_time_str])


@dataclass
class DecomposedFolder:
    subfolders: list[Subfolder]
    searches: list[Search]
    folder_name: str


def set_cloud_storage(folder_num: str) -> Blob:
    """sets the basic parameters for connection to txt file in cloud storage, which stores searches snapshots"""
    bucket_name = 'bucket_for_folders_snapshots'
    blob_name = str(folder_num) + '.txt'

    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)

    return blob


class CloudStorage:
    def read_searches(self, folder_num: str) -> str | None:
        return self._read_snapshot(f'{folder_num}_searches')

    def read_folders(self, folder_num: str) -> str | None:
        return self._read_snapshot(f'{folder_num}_folders')

    def write_searches(self, data: Any, folder_num: str) -> None:
        return self._write_snapshot(data, f'{folder_num}_searches')

    def write_folders(self, data: Any, folder_num: str) -> None:
        return self._write_snapshot(data, f'{folder_num}_folders')

    def _read_snapshot(self, snapshot_name: str) -> str | None:
        """reads previous searches snapshot from txt file in cloud storage"""

        try:
            blob = set_cloud_storage(snapshot_name)
            contents_as_bytes = blob.download_as_string()
            contents: str | None = str(contents_as_bytes, 'utf-8')
            if contents == 'None':
                contents = None
        except:  # noqa
            contents = None
        return contents

    def _write_snapshot(self, what_to_write: Any, snapshot_name: str) -> None:
        """writes current snapshot to txt file in cloud storage"""

        blob = set_cloud_storage(snapshot_name)
        blob.upload_from_string(str(what_to_write), content_type='text/plain')


class FolderComparator:
    def compare_folders(self, new_str: str, old_str: str | None) -> list[str]:
        """Compare if newly parsed folder content equals the previously-saved one."""
        if not old_str:
            return self._handle_new_folders(new_str)
        elif new_str != old_str:
            return self._handle_updated_folders(new_str, old_str)
        return []

    def _handle_new_folders(self, new_str: str) -> list[str]:
        """Handle case when there's no old version."""
        new_list = ast.literal_eval(new_str)
        return [n_line[0] for n_line in new_list]

    def _handle_updated_folders(self, new_str: str, old_str: str) -> list[str]:
        """Handle case when there are updates."""
        new_list = ast.literal_eval(new_str)
        old_list = ast.literal_eval(old_str)

        comparison_matrix = self._create_comparison_matrix(old_list, new_list)
        return self._find_changed_folders(comparison_matrix)

    def _create_comparison_matrix(self, old_list: list, new_list: list) -> list:
        """Create a matrix for comparing old and new folders."""
        comparison_matrix = [[o_line[0], o_line[1], ''] for o_line in old_list]

        for n_line in new_list:
            if not self._update_existing_folder(comparison_matrix, n_line):
                comparison_matrix.append([n_line[0], '', n_line[1]])

        return comparison_matrix

    def _update_existing_folder(self, comparison_matrix: list, n_line: list) -> bool:
        """Update existing folder in comparison matrix if found."""
        for m_line in comparison_matrix:
            if n_line[0] == m_line[0]:
                m_line[2] = n_line[1]
                return True
        return False

    def _find_changed_folders(self, comparison_matrix: list) -> list[str]:
        """Find folders that have changed based on comparison matrix."""
        return [line[0] for line in comparison_matrix if line[1] != line[2]]


class FolderDecomposer:
    def __init__(self) -> None:
        self.excluded_folder_nums = {84, 113, 112, 270, 86, 87, 88, 165, 365, 89, 172, 91, 90, 316, 234, 230, 319}

    def decompose_folder(self, start_folder_num: str) -> DecomposedFolder:
        """Check if there are changes in folder that contain other folders"""
        url = f'https://lizaalert.org/forum/viewforum.php?f={start_folder_num}'
        soup = self._fetch_and_parse_page(url)
        # we need to receive only text here
        # then we need to get subfolders and/or searches with BS4
        # and then we can mock it and test separately

        if not soup:
            return DecomposedFolder(subfolders=[], searches=[], folder_name='')

        folder_name = self._extract_folder_name(soup)
        page_summary_folders = self._get_subfolders(soup, start_folder_num)
        page_summary_searches = self._process_searches(soup, start_folder_num)

        logging.info(f'Page summary searches: {str(page_summary_searches)}')

        return DecomposedFolder(
            subfolders=page_summary_folders, searches=page_summary_searches, folder_name=folder_name
        )

    def _get_searches(self, soup: BeautifulSoup) -> list[Search]:
        return self._process_searches(soup, 'foo')

    def _fetch_and_parse_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch the page content and parse it with BeautifulSoup"""
        try:
            r = requests.Session().get(url)
            only_tag = SoupStrainer('div', {'class': 'page-body'})
            soup = BeautifulSoup(r.content, features='lxml', parse_only=only_tag)
            return soup
        except Exception as e:
            logging.info(f'Request to forum was unsuccessful for url {url}')
            logging.exception(e)
            return None

    def _extract_folder_name(self, soup: BeautifulSoup) -> str:
        """Extract the folder name from the parsed page"""
        try:
            folder_name = soup.find('h2', {'class': 'forum-title'}).next_element.next_element  # type:ignore[union-attr]
            logging.info(folder_name)
            return str(folder_name)
        except Exception:
            logging.info('Failed to extract folder name')
            return ''

    def _get_subfolders(self, soup: BeautifulSoup, start_folder_num: str) -> list[Subfolder]:
        """Process folder blocks and extract relevant information"""
        search_code_blocks_folders = soup.find_all('div', {'class': 'forabg'})
        page_summary_folders: list[Subfolder] = []

        if not search_code_blocks_folders:
            return page_summary_folders

        for block in search_code_blocks_folders:
            try:
                folders = block.find_all('li', {'class': 'row'})
                for folder in folders:
                    folder_num, folder_time_str = self._extract_folder_info(folder)
                    if not folder_num:
                        continue

                    if folder_num in self.excluded_folder_nums:
                        continue

                    page_summary_folders.append(Subfolder(folder_num=folder_num, change_time_str=folder_time_str))
            except Exception as e:
                logging.exception(f'Error in folder code blocks identification for {start_folder_num}')
        return page_summary_folders

    @no_type_check
    def _extract_folder_info(self, tag: Tag) -> tuple[int, str]:
        """Extract folder number and time from a folder element"""
        letters_before_forum_num = 18  # example: './viewforum.php?f=236'
        folder_num_str = tag.find('a', {'class': 'forumtitle'})['href']
        start_symb_to_del = folder_num_str.find('&sid=')
        folder_num = (
            int(folder_num_str[letters_before_forum_num:start_symb_to_del])
            if start_symb_to_del != -1
            else int(folder_num_str[letters_before_forum_num:])
        )

        try:
            folder_time_str = tag.find('time')['datetime']
        except:  # noqa
            folder_time_str = ''

        return folder_num, folder_time_str

    def _process_searches(self, soup: BeautifulSoup, start_folder_num: str) -> list[Search]:
        """Process search blocks and extract relevant information"""
        search_code_blocks_searches = soup.find_all('div', {'class': 'forumbg'})
        page_summary_searches: list[Search] = []
        try:
            if not search_code_blocks_searches:
                return page_summary_searches
            for block in search_code_blocks_searches:
                searches = block.find_all('dl', 'row-item')
                for i in range(len(searches) - 1):
                    search_title, search_time_str = self._extract_search_info(searches[i + 1])
                    page_summary_searches.append(Search(title=search_title, change_time_str=search_time_str))
        except Exception as e:
            logging.exception(f'Searches code blocks identification for {start_folder_num} was not successful')
        return page_summary_searches

    @no_type_check
    def _extract_search_info(self, tag: Tag) -> tuple[str, str]:
        """Extract search title and time from a search element"""
        search_title_block = tag.find('a', 'topictitle')
        search_title = search_title_block.next_element if search_title_block else ''

        try:
            search_time_str = tag.find('time')['datetime']
        except:  # noqa
            search_time_str = ''

        return search_title, search_time_str


def process_folder(
    folders_to_check: list[FolderForDecompose],
    updated_folders: list,
    folder: FolderForDecompose,
    storage: CloudStorage,
) -> None:
    decomposed_folder = FolderDecomposer().decompose_folder(folder.mother_folder_num)

    new_child_folders_str = str(decomposed_folder.subfolders)
    new_child_searches_str = str(decomposed_folder.searches)
    folder.mother_folder_name = decomposed_folder.folder_name

    old_child_folders_str = storage.read_folders(folder.mother_folder_num)
    old_child_searches_str = storage.read_searches(folder.mother_folder_num)

    list_of_new_folders = FolderComparator().compare_folders(new_child_folders_str, old_child_folders_str)

    storage.write_folders(new_child_folders_str, folder.mother_folder_num)
    storage.write_searches(new_child_searches_str, folder.mother_folder_num)

    logging.info(f'List of new folders in {folder.mother_folder_num}: {list_of_new_folders}')

    for line in list_of_new_folders:
        folders_to_check.append(FolderForDecompose(mother_folder_num=str(line)))

    if new_child_searches_str != old_child_searches_str:
        updated_folders.append((folder.mother_folder_num, folder.mother_folder_name))


def main(event: dict, context: Context) -> None:
    """main function"""

    storage = CloudStorage()

    folders_to_check: list[FolderForDecompose] = []
    updated_folders: list = []

    folders_to_scan_list_in_str = process_pubsub_message(event)
    folders_list_to_scan = ast.literal_eval(folders_to_scan_list_in_str)
    for folder_num, folder_name_ in folders_list_to_scan:
        folders_to_check.append(FolderForDecompose(mother_folder_num=folder_num))

    while folders_to_check:
        folder = folders_to_check.pop()
        process_folder(folders_to_check, updated_folders, folder, storage)

    logging.info('The below list is to be sent to "Identify updates of topics" script via pub/sub')
    logging.info(updated_folders)
    if updated_folders:
        publish_to_pubsub(Topics.topic_to_run_parsing_script, str(updated_folders))
