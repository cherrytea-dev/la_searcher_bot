from pathlib import Path

import pytest

from _dependencies.common.commons import ChangeType
from identify_updates_of_topics._utils.change_detector import ChangeDetector
from identify_updates_of_topics._utils.coordinates import CoordinatesResolver
from identify_updates_of_topics._utils.forum import ForumClient
from identify_updates_of_topics._utils.search_parser import SearchParser
from identify_updates_of_topics._utils.topic_updater import SearchUpdater
from tests.common import find_model
from tests.factories import db_factories, db_models
from tests.test_identify_updates_of_topics.factories import (
    ForumSearchItemFactory,
    SearchSummaryFactory,
)


class FakeForum(ForumClient):
    def _get_comment_content(self, search_num: int, comment_num: int) -> bytes:
        return Path('tests/fixtures/forum_comment.html').read_bytes()

    def _get_topic_content(self, search_num: int) -> bytes:
        return Path('tests/fixtures/forum_topic.html').read_bytes()


@pytest.fixture()
def searches_updater(db_client) -> SearchUpdater:
    forum = FakeForum()
    return SearchUpdater(
        db_client,
        forum,
        search_parser=SearchParser(CoordinatesResolver(db_client)),
        change_detector=ChangeDetector(),
        coordinates_resolver=CoordinatesResolver(db_client),
    )


class TestFolderUpdaterChangeLogCreation:
    def test_new_search(self, session, searches_updater: SearchUpdater):
        search_summary = SearchSummaryFactory.build()
        forum_search_item = ForumSearchItemFactory.build(
            search_id=search_summary.topic_id,
            raw_search_text='test raw text for activities parsing',
        )

        change_log_ids = searches_updater._update_change_log_and_search(search_summary, forum_search_item)

        assert len(change_log_ids) == 1
        assert find_model(session, db_models.ChangeLog, id=change_log_ids[0], change_type=ChangeType.topic_new)
        assert find_model(session, db_models.Search, search_forum_num=search_summary.topic_id)

    def test_changed_search(self, session, searches_updater: SearchUpdater):
        start_replies = 2
        search_summary = SearchSummaryFactory.build(
            num_of_replies=start_replies + 1,
        )
        db_factories.SearchFactory.create_sync(
            search_forum_num=search_summary.topic_id,
            forum_folder_id=search_summary.folder_id,
            num_of_replies=start_replies,
        )
        forum_search_item = ForumSearchItemFactory.build(
            search_id=search_summary.topic_id,
            raw_search_text='test raw text',
        )

        change_log_ids = searches_updater._update_change_log_and_search(search_summary, forum_search_item)

        assert len(change_log_ids) == 4
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
        assert find_model(
            session,
            db_models.ChangeLog,
            id=change_log_ids[2],
            change_type=ChangeType.topic_comment_new,
        )
        assert find_model(
            session,
            db_models.ChangeLog,
            id=change_log_ids[3],
            change_type=ChangeType.topic_inforg_comment_new,
        )
