from unittest.mock import MagicMock, Mock, patch

import pytest

from identify_updates_of_topics import main
from identify_updates_of_topics._utils.forum import ForumClient, ForumSearchItem
from tests.common import get_event_with_data

from .factories import ForumCommentItemFactory, ForumSearchItemFactory


def test_main():
    data = 'foo'
    with pytest.raises(ValueError):
        main.main(get_event_with_data(data), 'context')


def test_main_full_scenario(mock_http_get, patch_app_config):
    """Just run without errors"""

    search_id = 11
    data = [search_id]

    class FakeForum(ForumClient):
        def parse_search(self, search_num):
            return ForumSearchItemFactory.build()

        def get_raw_search_text(self, search_num):
            return 'foo'

        def get_comment_data(self, search_num, comment_num):
            return ForumCommentItemFactory.build()

        def get_replies_count(self, search_num):
            return 1

        def parse_coordinates_of_search(self, search_num):
            return [0.0, 0.0, '', '']

    with patch.object(main, 'ForumClient', FakeForum):
        main.main(get_event_with_data(data), Mock())
