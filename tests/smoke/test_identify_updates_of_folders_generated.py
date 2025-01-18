import pytest

from identify_updates_of_folders import main
from tests.common import run_smoke


def test_compare_old_and_new_folder_hash_and_give_list_of_upd_folders():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.compare_old_and_new_folder_hash_and_give_list_of_upd_folders)
    pass


def test_decompose_folder_to_subfolders_and_searches():
    res = run_smoke(main.decompose_folder_to_subfolders_and_searches)
    pass


def test_main():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.main)
    pass


def test_read_snapshot_from_cloud_storage():
    res = run_smoke(main.read_snapshot_from_cloud_storage)
    pass


def test_set_cloud_storage():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.set_cloud_storage)
    pass


def test_write_snapshot_to_cloud_storage():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.write_snapshot_to_cloud_storage)
    pass
