from unittest.mock import MagicMock, patch

import pytest
from google.cloud import storage

from identify_updates_of_folders import main
from tests.common import get_event_with_data


def test_main():
    # NO SMOKE TEST identify_updates_of_folders.main.main
    data = 'a = 1'
    event = get_event_with_data(data)
    with patch.object(storage.Client, '__init__', MagicMock(return_value=None)):
        with pytest.raises(SyntaxError):
            main.main(event, 'context')
        assert True


def test_set_cloud_storage():
    # NO SMOKE TEST identify_updates_of_folders.main.set_cloud_storage
    with patch('google.cloud.storage.Client'):
        main.set_cloud_storage(1)


def test_write_snapshot_to_cloud_storage():
    # NO SMOKE TEST identify_updates_of_folders.main.write_snapshot_to_cloud_storage
    with patch('google.cloud.storage.Client'):
        main.write_snapshot_to_cloud_storage('name', 1)


def test_compare_old_and_new_folder_hash_and_give_list_of_upd_folders():
    # NO SMOKE TEST identify_updates_of_folders.main.compare_old_and_new_folder_hash_and_give_list_of_upd_folders
    res = main.compare_old_and_new_folder_hash_and_give_list_of_upd_folders('["old"]', '["new"]')
    assert res == ['n', 'o']
