from unittest.mock import MagicMock

from check_topics_by_upd_time import main


def test_main():
    main.main(MagicMock(), 'context')
    assert True
