from unittest.mock import MagicMock, patch

from send_notifications import main


def test_main():
    # NO SMOKE TEST send_notifications.main.main
    with (
        patch('send_notifications.main.SCRIPT_SOFT_TIMEOUT_SECONDS', 1),
        patch('send_notifications.main.analytics_parsed_times', [1]),
    ):
        main.main(MagicMock(), 'context')
    assert True


def test_finish_time_analytics():
    # NO SMOKE TEST send_notifications.main.finish_time_analytics
    main.finish_time_analytics(notif_times=[1], delays=[1], parsed_times=[1], list_of_change_ids=[1])
