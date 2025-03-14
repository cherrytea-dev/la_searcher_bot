from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from identify_updates_of_topics import main
from identify_updates_of_topics._utils.forum import ForumClient
from tests.common import get_event_with_data


def test_main():
    data = 'foo'
    with pytest.raises(ValueError):
        main.main(get_event_with_data(data), 'context')
    assert True


def test_main_full_scenario(mock_http_get, patch_app_config):
    mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()

    forum_search_folder_id = 276
    data = [(forum_search_folder_id,)]
    context = Mock()
    context.event_id = 123
    with patch.object(ForumClient, 'parse_search_profile', Mock(return_value='foo')):
        main.main(get_event_with_data(str(data)), context)
