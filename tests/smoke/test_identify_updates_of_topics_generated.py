import pytest

from identify_updates_of_topics import main
from tests.common import run_smoke


def test_define_start_time_of_search():
    res = run_smoke(main.define_start_time_of_search)
    pass


def test_generate_random_function_id():
    res = run_smoke(main.generate_random_function_id)
    pass


def test_get_coordinates():
    res = run_smoke(main.get_coordinates)
    pass


def test_get_last_api_call_time_from_psql():
    res = run_smoke(main.get_last_api_call_time_from_psql)
    pass


def test_get_the_list_of_ignored_folders():
    res = run_smoke(main.get_the_list_of_ignored_folders)
    pass


def test_parse_coordinates():
    res = run_smoke(main.parse_coordinates)
    pass


def test_parse_one_folder():
    res = run_smoke(main.parse_one_folder)
    pass


def test_process_one_folder():
    res = run_smoke(main.process_one_folder)
    pass


def test_profile_get_managers():
    res = run_smoke(main.profile_get_managers)
    pass


def test_profile_get_type_of_activity():
    res = run_smoke(main.profile_get_type_of_activity)
    pass


def test_rate_limit_for_api():
    res = run_smoke(main.rate_limit_for_api)
    pass


def test_read_snapshot_from_cloud_storage():
    res = run_smoke(main.read_snapshot_from_cloud_storage)
    pass


def test_read_yaml_from_cloud_storage():
    res = run_smoke(main.read_yaml_from_cloud_storage)
    pass


def test_save_function_into_register():
    res = run_smoke(main.save_function_into_register)
    pass


def test_save_last_api_call_time_to_psql():
    res = run_smoke(main.save_last_api_call_time_to_psql)
    pass


def test_sql_connect():
    res = run_smoke(main.sql_connect)
    pass


def test_update_coordinates():
    res = run_smoke(main.update_coordinates)
    pass
