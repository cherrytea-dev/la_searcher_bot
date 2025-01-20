import pytest

from api_get_active_searches import main
from tests.common import run_smoke


def test_get_list_of_active_searches_from_db():
    res = run_smoke(main.get_list_of_active_searches_from_db)
    pass


def test_get_list_of_allowed_apps():
    res = run_smoke(main.get_list_of_allowed_apps)
    pass


def test_main():
    res = run_smoke(main.main)
    pass


def test_save_user_statistics_to_db():
    res = run_smoke(main.save_user_statistics_to_db)
    pass


def test_verify_json_validity():
    res = run_smoke(main.verify_json_validity)
    pass
