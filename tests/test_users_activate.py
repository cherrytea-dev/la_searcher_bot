from unittest.mock import MagicMock

from users_activate import main


def test_main():
    main.main(MagicMock(), 'context')
    assert True
