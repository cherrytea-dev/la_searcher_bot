import pytest

from identify_updates_of_first_posts import main
from tests.common import run_smoke


def test_age_writer():
    res = run_smoke(main.age_writer)
    pass


def test_clean_up_content():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.clean_up_content)
    pass


def test_compose_diff_message():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.compose_diff_message)
    pass


def test_generate_random_function_id():
    res = run_smoke(main.generate_random_function_id)
    pass


def test_get_compressed_first_post():
    res = run_smoke(main.get_compressed_first_post)
    pass


def test_get_field_trip_details_from_text():
    res = run_smoke(main.get_field_trip_details_from_text)
    pass


def test_get_the_list_of_coords_out_of_text():
    res = run_smoke(main.get_the_list_of_coords_out_of_text)
    pass


def test_main():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.main)
    pass


def test_parse_search_folder():
    res = run_smoke(main.parse_search_folder)
    pass


def test_process_first_page_comparison():
    res = run_smoke(main.process_first_page_comparison)
    pass


def test_process_pubsub_message():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.process_pubsub_message)
    pass


def test_save_function_into_register():
    res = run_smoke(main.save_function_into_register)
    pass


def test_save_new_record_into_change_log():
    res = run_smoke(main.save_new_record_into_change_log)
    pass


def test_split_text_to_deleted_and_regular_parts():
    res = run_smoke(main.split_text_to_deleted_and_regular_parts)
    pass


def test_sql_connect():
    res = run_smoke(main.sql_connect)
    pass
