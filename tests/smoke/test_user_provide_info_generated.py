import pytest

from tests.common import run_smoke
from user_provide_info import main


def test_clean_up_content():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.clean_up_content)
    pass


def test_evaluate_city_locations():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.evaluate_city_locations)
    pass


def test_get_user_data_from_db():
    res = run_smoke(main.get_user_data_from_db)
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


def test_verify_telegram_data():
    res = run_smoke(main.verify_telegram_data)
    pass


def test_verify_telegram_data_json():
    res = run_smoke(main.verify_telegram_data_json)
    pass


def test_verify_telegram_data_string():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.verify_telegram_data_string)
    pass
