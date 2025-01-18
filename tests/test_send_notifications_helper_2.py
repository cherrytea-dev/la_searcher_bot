from unittest.mock import MagicMock

from send_notifications_helper_2 import main


def test_main():
    main.main(MagicMock(), 'context')
    assert True
