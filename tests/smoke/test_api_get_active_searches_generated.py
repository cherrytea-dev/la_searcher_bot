import pytest

from api_get_active_searches import main
from tests.common import run_smoke


def test_clean_up_content():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.clean_up_content)
    pass


def test_evaluate_city_locations():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.evaluate_city_locations)
    pass


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


def test_time_counter_since_search_start():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.time_counter_since_search_start)
    pass


def test_verify_json_validity():
    res = run_smoke(main.verify_json_validity)
    pass
