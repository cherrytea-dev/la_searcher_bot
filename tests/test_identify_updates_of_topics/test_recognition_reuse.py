"""Recognition of a search title is a pure function of that title.

So a title that has not changed since the previous parse must not be sent to the `title_recognize`
cloud function again: the previous result is reused from the database.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from _dependencies.common.commons import TopicType
from _dependencies.forum.recognition_reuse import can_reuse_recognition
from identify_updates_of_topics._legacy._utils import database as legacy_database
from identify_updates_of_topics._legacy._utils import folder_updater as legacy_folder_updater
from identify_updates_of_topics._legacy._utils.folder_updater import FolderUpdater, KeyValueStorage
from identify_updates_of_topics._legacy._utils.topics_commons import (
    ForumSearchItem as LegacyForumSearchItem,
)
from identify_updates_of_topics._legacy._utils.topics_commons import (
    SearchSummary as LegacySearchSummary,
)
from identify_updates_of_topics._utils.topic_updater import SearchUpdater
from tests.factories import db_factories
from tests.test_identify_updates_of_topics.factories import ForumSearchItemFactory, SearchSummaryFactory

FOLDER_NUM = 276
SEARCH_ID = 101
PARSED_TIME = datetime(2026, 9, 15, 12, 0, 0)
UNCHANGED_TITLE = 'Пропал кот, Екатеринбург'
CHANGED_TITLE = 'Пропала собака, Екатеринбург'


def legacy_search_item(search_id: int, title: str, replies_count: int = 3) -> LegacyForumSearchItem:
    return LegacyForumSearchItem(
        title=title,
        search_id=search_id,
        replies_count=replies_count,
        start_datetime=PARSED_TIME,
    )


def legacy_search_summary(topic_id: int, title: str, name: str = 'Котова Мария') -> LegacySearchSummary:
    return LegacySearchSummary(
        topic_id=topic_id,
        folder_id=FOLDER_NUM,
        topic_type_id=TopicType.search_regular,
        topic_type='search',
        parsed_time=PARSED_TIME,
        status='Ищем',
        new_status='Ищем',
        title=title,
        start_time=PARSED_TIME,
        num_of_replies=3,
        name=name,
        display_name='Мария 40',
        age=40,
        age_min=40,
        age_max=40,
    )


def recognition_response(name: str = 'Найденный Иван') -> dict:
    """a response of the `title_recognize` cloud function for a regular search title"""

    return {
        'status': 'ok',
        'recognition': {
            'topic_type': 'search',
            'avia': False,
            'status': 'НЖ',
            'persons': {
                'total_persons': 1,
                'age_min': 30,
                'age_max': 30,
                'total_name': name,
                'total_display_name': 'Иван 30',
                'person': [],
            },
        },
    }


class FakeLegacyForum:
    """returns given items as a folder page, without touching the forum"""

    def __init__(self, items: list[LegacyForumSearchItem]) -> None:
        self.items = items

    def get_folder_searches(self, folder_id: int) -> list[LegacyForumSearchItem]:
        return self.items


class FakeSearchForum:
    """returns a given item as a search page, without touching the forum"""

    def __init__(self, item: object) -> None:
        self.item = item

    def parse_search(self, search_id: int) -> object:
        return self.item


@pytest.fixture()
def legacy_db_client(connection_pool) -> legacy_database.DBClient:
    return legacy_database.DBClient(connection_pool)


@pytest.fixture()
def recognized_titles(monkeypatch) -> list[str]:
    """collects titles sent to the recognition API instead of calling it"""

    titles: list[str] = []

    def fake_recognition(title: str, status_only: bool = False) -> dict:
        titles.append(title)
        return recognition_response()

    monkeypatch.setattr(legacy_folder_updater, 'recognize_title_via_api', fake_recognition)

    return titles


class TestCanReuseRecognition:
    def test_the_same_title_is_reused(self) -> None:
        assert can_reuse_recognition(UNCHANGED_TITLE, TopicType.search_regular, UNCHANGED_TITLE)

    def test_a_new_title_is_recognized(self) -> None:
        assert not can_reuse_recognition(UNCHANGED_TITLE, TopicType.search_regular, CHANGED_TITLE)

    def test_search_without_a_previous_parse_is_recognized(self) -> None:
        assert not can_reuse_recognition(None, None, UNCHANGED_TITLE)

    def test_failed_recognition_is_retried(self) -> None:
        assert not can_reuse_recognition(UNCHANGED_TITLE, None, UNCHANGED_TITLE)


class TestFolderUpdaterRecognitionReuse:
    def test_folder_without_updates_does_not_call_recognition(
        self,
        legacy_db_client,
        recognized_titles: list[str],
    ) -> None:
        items = [legacy_search_item(SEARCH_ID, UNCHANGED_TITLE), legacy_search_item(SEARCH_ID + 1, CHANGED_TITLE)]
        updater = FolderUpdater(legacy_db_client, FakeLegacyForum(items), FOLDER_NUM)
        KeyValueStorage(legacy_db_client).write_folder_hash(updater._make_snapshot_as_string(items), FOLDER_NUM)

        assert updater.run() == (False, [])
        assert recognized_titles == []

    def test_only_the_changed_title_is_recognized(
        self,
        legacy_db_client,
        recognized_titles: list[str],
    ) -> None:
        legacy_db_client.rewrite_snapshot_in_sql(
            FOLDER_NUM,
            [
                legacy_search_summary(SEARCH_ID, UNCHANGED_TITLE),
                legacy_search_summary(SEARCH_ID + 1, CHANGED_TITLE),
            ],
        )
        items = [legacy_search_item(SEARCH_ID, UNCHANGED_TITLE), legacy_search_item(SEARCH_ID + 1, 'Найдена!')]
        updater = FolderUpdater(legacy_db_client, FakeLegacyForum(items), FOLDER_NUM)

        swapped_summary, recognized_summary = updater._parse_one_folder(items)

        assert recognized_titles == ['Найдена!']
        assert recognized_summary.name == 'Найденный Иван'

        # результат прошлого распознавания переиспользован, а динамика взята со свежей страницы папки
        assert swapped_summary.title == UNCHANGED_TITLE
        assert swapped_summary.name == 'Котова Мария'
        assert swapped_summary.display_name == 'Мария 40'
        assert swapped_summary.topic_type_id == TopicType.search_regular
        assert swapped_summary.status == 'Ищем'
        assert swapped_summary.num_of_replies == 3


class TestSearchUpdaterRecognitionReuse:
    def test_unchanged_title_is_not_recognized_again(self, db_client, monkeypatch) -> None:
        item = ForumSearchItemFactory.build(title=UNCHANGED_TITLE)
        db_factories.SearchFactory.create_sync(
            search_forum_num=item.search_id,
            forum_search_title=item.title,
            forum_folder_id=item.folder_id,
        )
        search_parser = MagicMock()
        updater = SearchUpdater(db_client, FakeSearchForum(item), search_parser=search_parser)
        monkeypatch.setattr(updater, '_update_change_log_and_search', lambda *args, **kwargs: [])

        assert updater.update_search(item.search_id) == []
        search_parser.parse.assert_not_called()

    def test_changed_title_is_recognized(self, db_client, monkeypatch) -> None:
        item = ForumSearchItemFactory.build(title=CHANGED_TITLE)
        db_factories.SearchFactory.create_sync(
            search_forum_num=item.search_id,
            forum_search_title=UNCHANGED_TITLE,
            forum_folder_id=item.folder_id,
        )
        search_parser = MagicMock()
        search_parser.parse.return_value = SearchSummaryFactory.build(topic_id=item.search_id)
        updater = SearchUpdater(db_client, FakeSearchForum(item), search_parser=search_parser)
        monkeypatch.setattr(updater, '_update_change_log_and_search', lambda *args, **kwargs: [])

        assert updater.update_search(item.search_id) == []
        search_parser.parse.assert_called_once()

    def test_reuse_keeps_the_recognized_fields(self, db_client) -> None:
        item = ForumSearchItemFactory.build(title=UNCHANGED_TITLE)
        db_factories.SearchFactory.create_sync(
            search_forum_num=item.search_id,
            forum_search_title=item.title,
            forum_folder_id=item.folder_id,
            family_name='Котова Мария',
            display_name='Мария 40',
            status='Ищем',
            topic_type_id=TopicType.search_regular,
        )
        updater = SearchUpdater(db_client, FakeSearchForum(item), search_parser=MagicMock())
        prev_search = updater.db.get_search_by_id(item.search_id)
        assert prev_search is not None

        summary = updater._reuse_recognition(PARSED_TIME, item, prev_search)

        assert summary.name == 'Котова Мария'
        assert summary.display_name == 'Мария 40'
        assert summary.topic_type_id == TopicType.search_regular
        assert summary.status == 'Ищем'
