from unittest.mock import MagicMock

from compose_notifications import main


def test_main():
    main.main(MagicMock(), 'context')
    assert True
