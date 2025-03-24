from unittest.mock import MagicMock

from check_first_posts_for_changes import main


def test_main():
    main.main(MagicMock(), 'context')
    assert True


def test_generate_list_of_topic_groups():
    res = main.generate_list_of_topic_groups()
    assert len(res) == 20
