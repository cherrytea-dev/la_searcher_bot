from unittest.mock import MagicMock, patch

from send_notifications import main


def test_main():
    with (
        patch('send_notifications.main.SCRIPT_SOFT_TIMEOUT_SECONDS', 1),
        patch('send_notifications.main.analytics_parsed_times', [1]),
    ):
        main.main(MagicMock(), 'context')
    assert True
