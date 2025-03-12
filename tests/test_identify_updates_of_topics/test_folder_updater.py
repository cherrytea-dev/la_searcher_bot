from pathlib import Path
from unittest.mock import Mock, patch

from identify_updates_of_topics._utils.folder_updater import FolderUpdater
from identify_updates_of_topics._utils.forum import ForumClient


class TestFolderUpdater:
    def test_parse_one_folder(self, db, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()

        forum_search_folder_id = 276
        summaries, details = FolderUpdater(db, forum_search_folder_id)._parse_one_folder()
        assert summaries == [
            ['Жив Иванов Иван, 10 лет, ЗАО, г. Москва', 29],
            ['Пропал Петров Петр Петрович, 48 лет, ЗелАО, г. Москва - Тверская обл.', 116],
        ]
        assert len(details) == 2

    def test_process_one_folder(self, db, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()

        forum_search_folder_id = 276
        with patch.object(ForumClient, 'parse_search_profile', Mock(return_value='foo')):
            update_trigger, changed_ids = FolderUpdater(db, forum_search_folder_id).run()
        assert update_trigger is True

    def test_parse_one_comment(self, db, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_comment.html').read_bytes()

        there_are_inforg_comments = FolderUpdater(db, 1)._parse_and_write_one_comment(1, 1)
        assert there_are_inforg_comments

    def test_get_cordinates(self, db):
        data = 'Москва, Ярославское шоссе 123'
        with patch('identify_updates_of_topics._utils.folder_updater.rate_limit_for_api'):
            res = FolderUpdater(db, 1).get_coordinates_by_address(data)
        assert res == (None, None)

    def test_update_change_log_and_searches(self, db):
        res = FolderUpdater(db, 1)._update_change_log_and_searches()
        pass

    def test_parse_coordinates_of_search(db, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_topic.html').read_bytes()

        search_id = 1
        res = FolderUpdater(db, search_id)._parse_coordinates_of_search(search_id)
        assert res == (53.510722, 33.637365, '3. deleted coord')
