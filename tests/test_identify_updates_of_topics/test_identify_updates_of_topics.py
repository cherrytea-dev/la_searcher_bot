from unittest.mock import MagicMock, Mock, patch

import pytest

from identify_updates_of_topics import main
from tests.common import get_event_with_data


def test_main():
    data = 'foo'
    with pytest.raises(ValueError):
        main.main(get_event_with_data(data), 'context')


def test_main_full_scenario(mock_http_get, patch_app_config):
    search_id = 11
    data = [search_id]
    context = Mock()
    context.event_id = 123

    class FakeUpdater(main.SearchUpdater):
        pass

    with patch.object(main, 'SearchUpdater', FakeUpdater):
        main.main(get_event_with_data(data), context)

    # what to check here?
    pass
