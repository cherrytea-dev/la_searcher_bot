from unittest.mock import MagicMock

from manage_users import main


def test_main():
    main.main(MagicMock(), 'context')
    assert True
