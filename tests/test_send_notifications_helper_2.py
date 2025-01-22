from unittest.mock import MagicMock

from send_notifications_helper_2 import main


def test_main():
    # NO SMOKE TEST send_notifications_helper_2.main.main
    main.main(MagicMock(), 'context')
    assert True


def test_finish_time_analytics():
    # NO SMOKE TEST send_notifications_helper_2.main.finish_time_analytics
    main.finish_time_analytics(notif_times=[1], delays=[1], parsed_times=[1], list_of_change_ids=[1])
