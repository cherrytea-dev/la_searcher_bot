import pytest

from send_notifications_helper_2 import main
from tests.common import run_smoke


def test_check_and_save_event_id():
    res = run_smoke(main.check_and_save_event_id)
    pass


def test_check_first_notif_to_send():
    res = run_smoke(main.check_first_notif_to_send)
    pass


def test_check_for_notifs_to_send():
    res = run_smoke(main.check_for_notifs_to_send)
    pass


def test_finish_time_analytics():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.finish_time_analytics)
    pass


def test_generate_random_function_id():
    res = run_smoke(main.generate_random_function_id)
    pass


def test_get_change_log_update_time():
    res = run_smoke(main.get_change_log_update_time)
    pass


def test_get_triggering_function():
    res = run_smoke(main.get_triggering_function)
    pass


def test_iterate_over_notifications():
    res = run_smoke(main.iterate_over_notifications)
    pass


def test_main():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.main)
    pass


def test_process_pubsub_message():
    res = run_smoke(main.process_pubsub_message)
    pass


def test_process_response():
    res = run_smoke(main.process_response)
    pass


def test_save_sending_status_to_notif_by_user():
    res = run_smoke(main.save_sending_status_to_notif_by_user)
    pass


def test_send_location_to_api():
    res = run_smoke(main.send_location_to_api)
    pass


def test_send_message_to_api():
    res = run_smoke(main.send_message_to_api)
    pass


def test_send_single_message():
    res = run_smoke(main.send_single_message)
    pass
