from unittest.mock import MagicMock, Mock, patch

import pytest

from identify_updates_of_topics import main
from tests.common import get_event_with_data


def test_main():
    data = 'foo'
    with pytest.raises(ValueError):
        main.main(get_event_with_data(data), 'context')


def test_main_full_scenario(mock_http_get, patch_app_config):
    folder_num = 11
    data = [(folder_num,)]
    context = Mock()
    context.event_id = 123

    class FakeUpdater(main.FolderUpdater):
        walked_folders = []

        def __init__(self, db_client, forum, folder_num):
            self.__class__.walked_folders.append(folder_num)

        def run(self):
            return (False, [1, 2, 3])

    with patch.object(main, 'FolderUpdater', FakeUpdater):
        main.main(get_event_with_data(data), context)

    assert FakeUpdater.walked_folders == [folder_num]
