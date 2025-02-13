import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from check_topics_by_upd_time import main


@pytest.fixture
def patch_http():
    # disable common http patching
    pass


class FakeCloudStorage(main.CloudStorage):
    def __init__(self):
        self.data: dict[str, str] = {}

    def _read_snapshot(self, folder_num):
        return self.data.get(folder_num, None)

    def _write_snapshot(self, snapshot, folder_num):
        self.data[folder_num] = snapshot


@pytest.mark.freeze_time('2025-02-13 14:25:00')
def test_main_no_saved_folders(requests_mock):
    # NO SMOKE TEST check_topics_by_upd_time.main.main
    # NO SMOKE TEST check_topics_by_upd_time.main.get_the_list_folders_to_update

    text = Path('tests/fixtures/forum_main.html').read_text()

    requests_mock.get(
        'https://lizaalert.org/forum/index.php',
        text=text,
    )
    with (
        patch.object(main, 'publish_to_pubsub') as patched_pubsub,
        patch.object(main, 'CloudStorage', FakeCloudStorage),
    ):
        main.main('event', 'context')

    expected_folders = [
        [276, '2025-02-13T11:11:17+00:00'],
        [179, '2025-02-13T13:31:28+00:00'],
        [180, '2025-02-13T14:24:16+00:00'],
        [462, '2025-01-08T19:10:34+00:00'],
        [438, '2024-01-10T14:09:00+00:00'],
        [179, '2025-02-13T13:31:28+00:00'],
        [180, '2025-02-13T14:24:16+00:00'],
    ]
    assert patched_pubsub.call_args_list[0][0][1] == str(expected_folders)


def test_check_updates_in_folder_with_folders(requests_mock):
    text = Path('tests/fixtures/forum_main.html').read_text()

    requests_mock.get(
        'https://lizaalert.org/forum/index.php',
        text=text,
    )

    folder_checker = main.FolderUpdateChecker()
    page_summary = folder_checker.check_updates_in_folder_with_folders()
    parsed_folders_id = [int(folder[0]) for folder in page_summary]
    last_update_time = max(datetime.datetime.fromisoformat(x[1]) for x in page_summary)

    assert last_update_time == datetime.datetime(2025, 2, 13, 14, 24, 16, tzinfo=datetime.timezone.utc)
    assert page_summary
    assert 276 in parsed_folders_id  # Active searches
    assert 84 not in parsed_folders_id  # filtered folders, present in fixture file
    assert parsed_folders_id == [276, 179, 180, 462, 438, 179, 180]
