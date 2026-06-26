from unittest.mock import Mock, patch

import pytest

from identify_updates_of_topics import main
from identify_updates_of_topics._utils.forum import ForumClient
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
            return ForumSearchItemFactory.build(
                raw_search_text='foo',
                replies_count=1,
                lat=0.0,
                lon=0.0,
                coord_type='',
            )

        def get_comment_data(self, search_num, comment_num):
            return ForumCommentItemFactory.build()

    with patch.object(main, 'ForumClient', FakeForum):
        main.main(get_event_with_data(data), Mock())
