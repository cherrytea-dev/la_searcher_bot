from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from polyfactory.factories.dataclass_factory import DataclassFactory

from identify_updates_of_folders import main
from identify_updates_of_folders.main import (
    CloudStorage,
    DecomposedFolder,
    FolderComparator,
    FolderDecomposer,
    FolderForDecompose,
    Search,
    Subfolder,
    process_folder,
)
from tests.common import get_event_with_data


@pytest.fixture
def patch_http():
    # disable common http patching
    pass


class FakeCloudStorage(CloudStorage):
    def __init__(self):
        self.data: dict[str, str] = {}

    def _read_snapshot(self, folder_num):
        return self.data.get(folder_num, None)

    def _write_snapshot(self, snapshot, folder_num):
        self.data[folder_num] = snapshot


class SearchFactory(DataclassFactory[Search]):
    pass


class SubfolderFactory(DataclassFactory[Subfolder]):
    pass


class DecomposedFolderFactory(DataclassFactory[DecomposedFolder]):
    pass


class FakeFolderDecomposer(FolderDecomposer):
    folders = SubfolderFactory.batch(3)
    searches = SearchFactory.batch(3)

    forum_pages = {
        folders[0].folder_num: DecomposedFolder(
            subfolders=[folders[1], folders[2]], searches=[searches[0]], folder_name='f1'
        ),
        folders[1].folder_num: DecomposedFolder(subfolders=[], searches=[], folder_name='f2'),
        folders[2].folder_num: DecomposedFolder(subfolders=[], searches=[searches[1], searches[2]], folder_name='f3'),
    }

    def decompose_folder(self, folder_num: str):
        return self.forum_pages[int(folder_num)]


def test_main():
    # NO SMOKE TEST identify_updates_of_folders.main.main
    folders = FakeFolderDecomposer.folders
    start_folder_num = folders[0].folder_num
    data = f"[('{start_folder_num}', None)]"
    event = get_event_with_data(data)
    with (
        patch.object(main, 'CloudStorage', FakeCloudStorage),
        patch.object(main, 'FolderDecomposer', FakeFolderDecomposer),
        patch.object(main, 'publish_to_pubsub') as patched_pubsub,
    ):
        main.main(event, 'context')

        message = [
            (str(folders[0].folder_num), 'f1'),
            (str(folders[2].folder_num), 'f3'),
            (str(folders[1].folder_num), 'f2'),
        ]
        patched_pubsub.assert_called_once()
        assert patched_pubsub.call_args[0][1] == str(message)


def test_compare_old_and_new_folder_hash_and_give_list_of_upd_folders():
    res = main.FolderComparator().compare_folders('["old"]', '["new"]')
    assert res == ['n', 'o']


def test_handle_updated_folders_with_duplicates():
    new_str = '[[1, "2023-05-01"], [2, "2023-05-02"], [1, "2023-05-03"], [3, "2023-05-04"]]'
    old_str = '[[1, "2023-05-01"], [2, "2023-05-02"], [1, "2023-05-01"], [4, "2023-05-05"]]'

    result = FolderComparator()._handle_updated_folders(new_str, old_str)

    assert result == [1, 1, 4, 3]


class TestCompareFolders:
    def test_compare_old_and_new_folder_hash_empty_strings(self):
        new_str = '[]'
        old_str = '[]'
        result = FolderComparator().compare_folders(new_str, old_str)
        assert result == []

    def test_compare_folders_with_empty_old_str(self):
        new_str = '[[1, "2023-01-01"], [2, "2023-01-02"], [3, "2023-01-03"]]'
        old_str = ''
        result = FolderComparator().compare_folders(new_str, old_str)
        assert result == [1, 2, 3]

    def test_compare_folders_with_identical_strings(self):
        new_str = '[[1, "2023-01-01"], [2, "2023-01-02"], [3, "2023-01-03"]]'
        old_str = '[[1, "2023-01-01"], [2, "2023-01-02"], [3, "2023-01-03"]]'
        result = FolderComparator().compare_folders(new_str, old_str)
        assert result == []

    def test_compare_folders_with_updates(self):
        new_str = '[[1, "2023-01-01"], [2, "2023-01-02"], [3, "2023-01-03"], [4, "2023-01-04"]]'
        old_str = '[[1, "2023-01-01"], [2, "2023-01-01"], [3, "2023-01-03"]]'
        result = FolderComparator().compare_folders(new_str, old_str)
        assert result == [2, 4]

    def test_compare_folders_with_new_folders(self):
        new_str = '[[1, "2023-01-01"], [2, "2023-01-02"], [3, "2023-01-03"], [4, "2023-01-04"]]'
        old_str = '[[1, "2023-01-01"], [2, "2023-01-02"]]'
        result = FolderComparator().compare_folders(new_str, old_str)
        assert result == [3, 4]

    def test_compare_folders_with_removed_folders(self):
        new_str = '[[1, "2023-01-01"], [3, "2023-01-03"]]'
        old_str = '[[1, "2023-01-01"], [2, "2023-01-02"], [3, "2023-01-03"]]'
        result = FolderComparator().compare_folders(new_str, old_str)
        assert result == [2]

    def test_compare_folders_with_large_inputs(self):
        new_str = '[[1, "2023-01-01"], [2, "2023-01-02"], [3, "2023-01-03"], [4, "2023-01-04"], [5, "2023-01-05"], [6, "2023-01-06"], [7, "2023-01-07"], [8, "2023-01-08"], [9, "2023-01-09"], [10, "2023-01-10"]]'
        old_str = '[[1, "2023-01-01"], [2, "2023-01-01"], [3, "2023-01-03"], [4, "2023-01-03"], [5, "2023-01-05"], [6, "2023-01-05"], [7, "2023-01-07"], [8, "2023-01-07"]]'
        result = FolderComparator().compare_folders(new_str, old_str)
        assert result == [2, 4, 6, 8, 9, 10]

    def test_compare_folders_with_special_characters(self):
        new_str = '[[1, "2023-01-01"], [2, "2023-01-02"], [3, "Folder with spaces!"], [4, "Folder@with@symbols"]]'
        old_str = '[[1, "2023-01-01"], [2, "2023-01-01"], [3, "Old folder name"]]'
        result = FolderComparator().compare_folders(new_str, old_str)
        assert result == [2, 3, 4]

    def test_compare_folders_with_empty_hashes(self):
        new_str = '[[1, "2023-01-01"], [2, ""], [3, "2023-01-03"]]'
        old_str = '[[1, "2023-01-01"], [2, "2023-01-02"], [3, ""]]'
        result = FolderComparator().compare_folders(new_str, old_str)
        assert result == [2, 3]

    def test_compare_folders_invalid_input(self):
        with pytest.raises(SyntaxError):
            FolderComparator().compare_folders('invalid input', "[[1, '2023-01-01']]")


class TestDecomposeFolderToSubfolders:
    def test_decompose_folder_to_subfolders_and_searches_no_forum_title(self, requests_mock):
        requests_mock.get('https://lizaalert.org/forum/viewforum.php?f=123', text='<div class="page-body"></div>')
        result = FolderDecomposer().decompose_folder('123')

        assert result == DecomposedFolder(subfolders=[], searches=[], folder_name='')

    def test_no_folders_and_2_searches(self, requests_mock):
        text = Path('tests/fixtures/forum_folder_276.html').read_text()

        requests_mock.get(
            'https://lizaalert.org/forum/viewforum.php?f=276',
            text=text,
        )

        result = FolderDecomposer().decompose_folder('276')

        assert not result.subfolders
        assert result.searches == [
            Search(title='Жив Иванов Иван, 10 лет, ЗАО, г. Москва', change_time_str='2025-01-14T06:36:15+00:00'),
            Search(
                title='Пропал Петров Петр Петрович, 48 лет, ЗелАО, г. Москва - Тверская обл.',
                change_time_str='2024-11-17T16:23:11+00:00',
            ),
        ]
        assert result.folder_name == 'Активные поиски'

    def test_decompose_folder_to_subfolders_and_searches_parses_search_titles_and_timestamps(self, requests_mock):
        content = """
        <div class="page-body">
            <h2 class="forum-title">Test Forum</h2>
            <div class="forumbg">
                <dl class="row-item">
                    <a class="topictitle">Search 1</a>
                    <time datetime="2023-05-01T12:00:00+00:00"></time>
                </dl>
                <dl class="row-item">
                    <a class="topictitle">Search 2</a>
                    <time datetime="2023-05-02T14:30:00+00:00"></time>
                </dl>
            </div>
        </div>
        """
        requests_mock.get(
            'https://lizaalert.org/forum/viewforum.php?f=123',
            text=content,
        )

        result = FolderDecomposer().decompose_folder('123')

        assert result.searches == [Search(title='Search 2', change_time_str='2023-05-02T14:30:00+00:00')]

    def test_decompose_folder_to_subfolders_and_searches_missing_time_attribute(self, requests_mock):
        content = """
       <div class="page-body">
           <h2 class="forum-title">Test Forum</h2>
           <div class="forabg">
               <li class="row">
                   <a class="forumtitle" href="viewforum.php?f=  123">Test Folder</a>
                   <!-- No time element -->
               </li>
           </div>
       </div>
       """
        requests_mock.get(
            'https://lizaalert.org/forum/viewforum.php?f=123',
            text=content,
        )

        result = FolderDecomposer().decompose_folder('123')

        assert result.subfolders == [
            Subfolder(folder_num=123, change_time_str='')
        ]  # Check that folder is added with None as time
        assert not result.searches

    def test_decompose_folder_to_subfolders_and_searches_excludes_specified_folders(self, requests_mock):
        content = """
        <div class="page-body">
            <h2 class="forum-title"></h2>
            <span>Test Forum</span>
            <div class="forabg">
                <li class="row">
                    <a class="forumtitle" href="12345678901234567-84"></a>
                    <time datetime="2023-05-01T12:00:00+00:00"></time>
                </li>
                <li class="row">
                    <a class="forumtitle" href="12345678901234567-100"></a>
                    <time datetime="2023-05-02T14:30:00+00:00"></time>
                </li>
                <li class="row">
                    <a class="forumtitle" href="12345678901234567-319"></a>
                    <time datetime="2023-05-03T16:45:00+00:00"></time>
                </li>
            </div>
        </div>
        """
        requests_mock.get('https://lizaalert.org/forum/viewforum.php?f=123', text=content)

        result = FolderDecomposer().decompose_folder('123')

        assert result.subfolders == [Subfolder(folder_num=100, change_time_str='2023-05-02T14:30:00+00:00')]

    def test_get_folders_and_searches(self, requests_mock):
        text = Path('tests/fixtures/forum_folder_179_with_subfolders.html').read_text()

        requests_mock.get(
            'https://lizaalert.org/forum/viewforum.php?f=179',
            text=text,
        )

        result = FolderDecomposer().decompose_folder('179')
        assert result.searches == [
            Search(
                title='Пропала Иванова Лидия 77 лет, г. Моршанск, Тамбовская обл.',
                change_time_str='2024-07-15T10:31:20+00:00',
            ),
            Search(
                title='Жив Иванов Иван 55 лет, Чистые пруды, Тамбовская обл.',
                change_time_str='2024-07-14T15:19:52+00:00',
            ),
        ]
        assert result.subfolders == [
            Subfolder(236, '2025-02-03T21:24:44+00:00'),
            Subfolder(138, '2025-02-08T13:52:23+00:00'),
            Subfolder(123, '2025-02-09T15:42:45+00:00'),
        ]


class TestProcessFolder:
    # NO SMOKE TEST identify_updates_of_folders.main.process_folder
    def test_process_folder_not_been_in_storage(self, requests_mock):
        text = Path('tests/fixtures/forum_folder_179_with_subfolders.html').read_text()
        requests_mock.get(
            'https://lizaalert.org/forum/viewforum.php?f=179',
            text=text,
        )
        folders_to_check: list[FolderForDecompose] = []
        updated_folders = []
        folder = FolderForDecompose(mother_folder_num='179')
        fake_storage = FakeCloudStorage()
        process_folder(folders_to_check, updated_folders, folder, fake_storage)
        assert fake_storage.data['179_folders']
        assert fake_storage.data['179_searches']

        assert len(folders_to_check) == 3
        assert folders_to_check[0].mother_folder_num == '236'
        assert folders_to_check[1].mother_folder_num == '138'
        assert folders_to_check[2].mother_folder_num == '123'

    def test_process_folder_have_been_in_storage(self, requests_mock):
        """All three folders from fixture file already saved in cloud storage.
        we don't need to walk them"""
        text = Path('tests/fixtures/forum_folder_179_with_subfolders.html').read_text()
        requests_mock.get(
            'https://lizaalert.org/forum/viewforum.php?f=179',
            text=text,
        )
        updated_folders = []
        folders_to_check: list[FolderForDecompose] = []
        folder = FolderForDecompose(mother_folder_num='179')
        fake_storage = FakeCloudStorage()
        fake_storage.data['179_folders'] = (
            "[[236, '2025-02-03T21:24:44+00:00'], [138, '2025-02-08T13:52:23+00:00'], [123, '2025-02-09T15:42:45+00:00']]"
        )
        process_folder(folders_to_check, updated_folders, folder, fake_storage)
        assert not folders_to_check

    def test_process_folder_modified_in_storage(self, requests_mock):
        """Folder 123 was modifies, folder 236 was not present in cloud storage. They both should be walked"""
        text = Path('tests/fixtures/forum_folder_179_with_subfolders.html').read_text()
        requests_mock.get(
            'https://lizaalert.org/forum/viewforum.php?f=179',
            text=text,
        )
        updated_folders = []
        folders_to_check: list[FolderForDecompose] = []
        folder = FolderForDecompose(mother_folder_num='179')
        fake_storage = FakeCloudStorage()
        fake_storage.data['179_folders'] = "[[138, '2025-02-08T13:52:23+00:00'], [123, '2000-02-09T15:42:45+00:00']]"

        process_folder(folders_to_check, updated_folders, folder, fake_storage)
        assert fake_storage.data['179_folders']
        assert fake_storage.data['179_searches']

        assert len(folders_to_check) == 2
        assert folders_to_check[0].mother_folder_num == '123'
        assert folders_to_check[1].mother_folder_num == '236'
