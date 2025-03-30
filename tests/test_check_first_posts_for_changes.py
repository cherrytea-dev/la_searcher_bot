from unittest.mock import MagicMock

from check_first_posts_for_changes import main


def test_main():
    main.main(MagicMock(), 'context')
    assert True
