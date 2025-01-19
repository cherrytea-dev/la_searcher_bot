import pytest

from manage_topics import main
from tests.common import run_smoke


def test_generate_random_function_id():
    res = run_smoke(main.generate_random_function_id)
    pass


def test_main():
    res = run_smoke(main.main)
    pass


def test_save_function_into_register():
    res = run_smoke(main.save_function_into_register)
    pass


def test_save_status_for_topic():
    res = run_smoke(main.save_status_for_topic)
    pass


def test_save_visibility_for_topic():
    res = run_smoke(main.save_visibility_for_topic)
    pass


def test_sql_connect():
    res = run_smoke(main.sql_connect)
    pass
