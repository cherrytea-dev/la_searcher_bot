from unittest.mock import MagicMock

from archive_notifications import main


def test_main():
    main.main(MagicMock(), 'context')
    assert True
