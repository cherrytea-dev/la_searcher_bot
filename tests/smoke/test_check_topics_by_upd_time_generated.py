import pytest

from check_topics_by_upd_time import main
from tests.common import run_smoke


def test_check_updates_in_folder_with_folders():
    res = run_smoke(main.check_updates_in_folder_with_folders)
    pass


def test_get_the_list_folders_to_update():
    res = run_smoke(main.get_the_list_folders_to_update)
    pass


def test_main():
    res = run_smoke(main.main)
    pass


def test_notify_admin():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.notify_admin)
    pass


def test_time_delta():
    res = run_smoke(main.time_delta)
    pass
