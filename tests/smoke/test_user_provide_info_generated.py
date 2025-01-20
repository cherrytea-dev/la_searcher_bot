import pytest

from tests.common import run_smoke
from user_provide_info import main


def test_get_user_data_from_db():
    res = run_smoke(main.get_user_data_from_db)
    pass


def test_main():
    res = run_smoke(main.main)
    pass


def test_save_user_statistics_to_db():
    res = run_smoke(main.save_user_statistics_to_db)
    pass


def test_verify_telegram_data():
    res = run_smoke(main.verify_telegram_data)
    pass


def test_verify_telegram_data_json():
    res = run_smoke(main.verify_telegram_data_json)
    pass
