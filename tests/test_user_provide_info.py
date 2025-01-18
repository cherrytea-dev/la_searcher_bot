from unittest.mock import MagicMock

from user_provide_info import main


def test_main():
    main.main(MagicMock())
    assert True
