from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from _dependencies.commons import ChangeType
from identify_updates_of_topics._utils.folder_updater import FolderUpdater
from identify_updates_of_topics._utils.forum import ForumClient
from identify_updates_of_topics._utils.topics_commons import ForumCommentItem
from tests.common import find_model
from tests.factories import db_factories, db_models
from tests.test_identify_updates_of_topics.factories import SearchSummaryFactory, fake


class PatchedFolderUpdater(FolderUpdater):
    forum: 'FakeForum'


@pytest.fixture()
def folder_updater(db_client) -> PatchedFolderUpdater:
    return PatchedFolderUpdater(db_client, FakeForum(), fake.pyint())


class FakeForum(ForumClient):
    def parse_search_profile(self, search_num: int) -> str:
        # return super().parse_search_profile(search_num)
        return f'Profile for search {search_num}'

    def parse_coordinates_of_search(self, search_num):
        return super().parse_coordinates_of_search(search_num)

    def get_folder_searches(self, folder_id):
        return super().get_folder_searches(folder_id)

    def get_comment_data(self, search_num, comment_num) -> ForumCommentItem:
        return super().get_comment_data(search_num, comment_num)

    def setup(self, searches=None, comments=None, search_coords=None, search_summaries=None) -> None:
        pass


class TestFolderUpdater:
    def test_parse_one_folder(self, mock_http_get, folder_updater: PatchedFolderUpdater):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()

        summaries, details = folder_updater._parse_one_folder()

        assert summaries == [
            ['Жив Иванов Иван, 10 лет, ЗАО, г. Москва', 29],
            ['Пропал Петров Петр Петрович, 48 лет, ЗелАО, г. Москва - Тверская обл.', 116],
        ]
        assert len(details) == 2

    def test_process_one_folder(self, mock_http_get, folder_updater: PatchedFolderUpdater):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()

        with patch.object(folder_updater.forum, 'parse_search_profile', Mock(return_value='foo')):
            update_trigger, changed_ids = folder_updater.run()

        assert update_trigger is True


class TestFolderUpdaterChangeLogCreation:
    def test_new_search(self, session, folder_updater: PatchedFolderUpdater):
        search_summary = SearchSummaryFactory.build(folder_id=folder_updater.folder_num)

        change_log_ids = folder_updater._update_change_log_and_searches([search_summary])

        assert len(change_log_ids) == 1
        assert find_model(session, db_models.ChangeLog, id=change_log_ids[0], change_type=ChangeType.topic_new)
        assert find_model(session, db_models.Search, search_forum_num=search_summary.topic_id)

    def test_changed_search(self, session, folder_updater: PatchedFolderUpdater):
        search_summary = SearchSummaryFactory.build(folder_id=folder_updater.folder_num)
        existed_search = db_factories.SearchFactory.create_sync(
            search_forum_num=search_summary.topic_id,
            forum_folder_id=search_summary.folder_id,
        )

        change_log_ids = folder_updater._update_change_log_and_searches([search_summary])

        assert len(change_log_ids) == 2
        assert find_model(
            session,
            db_models.ChangeLog,
            id=change_log_ids[0],
            change_type=ChangeType.topic_status_change,
        )
        assert find_model(
            session,
            db_models.ChangeLog,
            id=change_log_ids[1],
            change_type=ChangeType.topic_title_change,
        )


class TestFolderUpdaterChangeDetection:
    def test_no_changes(self, folder_updater: PatchedFolderUpdater):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)

        changes = folder_updater._detect_changes(snapshot, search, False)

        assert not changes

    def test_changed_title(self, folder_updater: PatchedFolderUpdater):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)
        search.title = 'New Title'

        changes = folder_updater._detect_changes(snapshot, search, False)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.topic_title_change

    def test_changed_status(self, folder_updater: PatchedFolderUpdater):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)
        search.status = 'New Status'

        changes = folder_updater._detect_changes(snapshot, search, False)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.topic_status_change

    def test_changed_num_of_replies_no_inforg(self, folder_updater: PatchedFolderUpdater):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)
        search.num_of_replies -= 1

        changes = folder_updater._detect_changes(snapshot, search, False)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.topic_comment_new

    def test_changed_num_of_replies_inforg(self, folder_updater: PatchedFolderUpdater):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)
        search.num_of_replies -= 1

        changes = folder_updater._detect_changes(snapshot, search, True)

        assert len(changes) == 2
        assert changes[0].change_type == ChangeType.topic_comment_new
        assert changes[1].change_type == ChangeType.topic_inforg_comment_new
