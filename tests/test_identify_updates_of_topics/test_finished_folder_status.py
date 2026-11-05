"""Tests for marking searches as finished based on forum folder subtype (#793)."""

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from _dependencies.common.commons import ChangeType, TopicType
from _dependencies.forum.recognition_schema import RecognitionTopicType
from identify_updates_of_topics._legacy._utils import database as legacy_database
from identify_updates_of_topics._legacy._utils import folder_updater as legacy_folder_updater
from identify_updates_of_topics._legacy._utils.folder_updater import FolderUpdater
from identify_updates_of_topics._legacy._utils.topics_commons import (
    ForumSearchItem as LegacyForumSearchItem,
)
from identify_updates_of_topics._utils import search_parser as search_parser_module
from identify_updates_of_topics._utils.change_detector import ChangeDetector
from identify_updates_of_topics._utils.coordinates import CoordinatesResolver
from identify_updates_of_topics._utils.database import DBClient
from identify_updates_of_topics._utils.forum import ForumClient
from identify_updates_of_topics._utils.search_parser import SearchParser, resolve_search_status
from identify_updates_of_topics._utils.topic_updater import SearchUpdater
from identify_updates_of_topics._utils.topics_commons import ForumSearchItem
from tests.common import find_model
from tests.factories import db_factories, db_models
from tests.test_identify_updates_of_topics.factories import ForumSearchItemFactory

pytestmark = pytest.mark.xdist_group('finished_folder_status')

ACTIVE_FOLDER_ID = 276  # Свердловская обл. – Активные поиски
FINISHED_FOLDER_ID = 275  # Свердловская обл. – Завершенные поиски
EVENTS_FOLDER_ID = 367  # Вологодская обл. – Мероприятия
PARSED_TIME = datetime(2026, 10, 26, 12, 0, 0)
NEUTRAL_SEARCH_TITLE = 'Пропал Иванов Иван Иванович, 35 лет, г. Екатеринбург'


def _reco_payload(topic_type: str = 'search', status: str | None = 'Ищем') -> dict:
    payload: dict = {
        'topic_type': topic_type,
        'avia': False,
        'status': status,
    }
    if topic_type not in {'event', 'info', 'UNRECOGNIZED'}:
        payload['persons'] = {
            'total_persons': 1,
            'age_min': 35,
            'age_max': 35,
            'total_name': 'Иванов',
            'total_display_name': 'Иванов 35',
            'person': [],
        }
    return {'status': 'ok', 'recognition': payload}


class _SingleItemForum(ForumClient):
    def __init__(self, item: ForumSearchItem) -> None:
        self._item = item

    def parse_search(self, search_num: int) -> ForumSearchItem | None:
        return self._item


class _LegacyListForum(legacy_folder_updater.ForumClient):
    def __init__(self, items: list[LegacyForumSearchItem]) -> None:
        self._items = items

    def get_folder_searches(self, folder_id: int) -> list[LegacyForumSearchItem]:
        return self._items


class TestFinishedFoldersQuery:
    def test_returns_only_searches_finished_folders(self, db_client: DBClient, connection_pool) -> None:
        finished_ids = set(db_client.get_folders_with_finished_searches())
        legacy_finished_ids = set(legacy_database.DBClient(connection_pool).get_folders_with_finished_searches())

        assert FINISHED_FOLDER_ID in finished_ids
        assert ACTIVE_FOLDER_ID not in finished_ids
        assert EVENTS_FOLDER_ID not in finished_ids
        assert finished_ids == legacy_finished_ids


class TestResolveSearchStatus:
    @pytest.mark.parametrize('recognized_status', ['Ищем', 'СТОП', None, 'Завершен'])
    def test_search_without_exact_terminal_status_in_finished_folder_becomes_finished(
        self, recognized_status: str | None
    ) -> None:
        result = resolve_search_status(
            recognized_status=recognized_status,
            topic_type=RecognitionTopicType.search,
            folder_id=FINISHED_FOLDER_ID,
            folders_with_finished_searches={FINISHED_FOLDER_ID},
        )
        assert result == 'Завершен'

    @pytest.mark.parametrize('terminal_status', ['НЖ', 'НП', 'Найден'])
    def test_exact_terminal_status_from_title_is_preserved_in_finished_folder(self, terminal_status: str) -> None:
        result = resolve_search_status(
            recognized_status=terminal_status,
            topic_type=RecognitionTopicType.search,
            folder_id=FINISHED_FOLDER_ID,
            folders_with_finished_searches={FINISHED_FOLDER_ID},
        )
        assert result == terminal_status

    def test_active_folder_keeps_recognized_status(self) -> None:
        result = resolve_search_status(
            recognized_status='Ищем',
            topic_type=RecognitionTopicType.search,
            folder_id=ACTIVE_FOLDER_ID,
            folders_with_finished_searches={FINISHED_FOLDER_ID},
        )
        assert result == 'Ищем'

    @pytest.mark.parametrize(
        'non_search_type',
        [RecognitionTopicType.event, RecognitionTopicType.info, RecognitionTopicType.unrecognized],
    )
    def test_event_and_info_topics_keep_their_status(self, non_search_type: RecognitionTopicType) -> None:
        result = resolve_search_status(
            recognized_status=None,
            topic_type=non_search_type,
            folder_id=FINISHED_FOLDER_ID,
            folders_with_finished_searches={FINISHED_FOLDER_ID},
        )
        assert result is None

    def test_parser_keeps_event_folder_topic_unchanged_even_if_folder_marked_finished(
        self, db_client: DBClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            search_parser_module,
            'recognize_title_via_api',
            lambda title, status_only=False: _reco_payload(topic_type='search', status='Ищем'),
        )
        parser = SearchParser(CoordinatesResolver(db_client))
        item = ForumSearchItemFactory.build(
            title=NEUTRAL_SEARCH_TITLE,
            folder_id=EVENTS_FOLDER_ID,
            replies_count=0,
        )

        summary = parser.parse(
            PARSED_TIME,
            item,
            folders_with_events={EVENTS_FOLDER_ID},
            folders_with_finished_searches={EVENTS_FOLDER_ID},
        )

        assert summary is not None
        assert summary.topic_type == RecognitionTopicType.event
        assert summary.status == 'Ищем'
        assert summary.new_status == 'Ищем'


class TestSearchUpdaterFolderTransitions:
    def test_move_from_active_to_finished_folder_creates_status_change_to_finished(
        self,
        session: Session,
        db_client: DBClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        search_id = 793001
        db_factories.SearchFactory.create_sync(
            search_forum_num=search_id,
            forum_search_title=NEUTRAL_SEARCH_TITLE,
            forum_folder_id=ACTIVE_FOLDER_ID,
            status='Ищем',
            topic_type='search',
            topic_type_id=TopicType.search_regular,
            num_of_replies=2,
        )

        api_calls: list[str] = []

        def unexpected_api(title: str, status_only: bool = False) -> dict:
            api_calls.append(title)
            return _reco_payload(status='Ищем')

        monkeypatch.setattr(search_parser_module, 'recognize_title_via_api', unexpected_api)

        moved_item = ForumSearchItemFactory.build(
            search_id=search_id,
            title=NEUTRAL_SEARCH_TITLE,
            folder_id=FINISHED_FOLDER_ID,
            replies_count=2,
        )
        updater = SearchUpdater(
            db_client,
            _SingleItemForum(moved_item),
            search_parser=SearchParser(CoordinatesResolver(db_client)),
            change_detector=ChangeDetector(),
            coordinates_resolver=CoordinatesResolver(db_client),
        )

        change_log_ids = updater.update_search(search_id)

        assert api_calls == []
        assert len(change_log_ids) == 1
        change_log = find_model(session, db_models.ChangeLog, id=change_log_ids[0])
        assert change_log.change_type == ChangeType.topic_status_change
        assert change_log.new_value == 'Завершен'

        updated_search = find_model(session, db_models.Search, search_forum_num=search_id)
        assert updated_search.status == 'Завершен'
        assert updated_search.forum_folder_id == FINISHED_FOLDER_ID

    def test_move_from_finished_to_active_folder_restores_title_status(
        self,
        session: Session,
        db_client: DBClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        search_id = 793002
        db_factories.SearchFactory.create_sync(
            search_forum_num=search_id,
            forum_search_title=NEUTRAL_SEARCH_TITLE,
            forum_folder_id=FINISHED_FOLDER_ID,
            status='Завершен',
            topic_type='search',
            topic_type_id=TopicType.search_regular,
            num_of_replies=4,
        )
        monkeypatch.setattr(
            search_parser_module,
            'recognize_title_via_api',
            lambda title, status_only=False: _reco_payload(topic_type='search', status='Ищем'),
        )

        reopened_item = ForumSearchItemFactory.build(
            search_id=search_id,
            title=NEUTRAL_SEARCH_TITLE,
            folder_id=ACTIVE_FOLDER_ID,
            replies_count=4,
        )
        updater = SearchUpdater(
            db_client,
            _SingleItemForum(reopened_item),
            search_parser=SearchParser(CoordinatesResolver(db_client)),
            change_detector=ChangeDetector(),
            coordinates_resolver=CoordinatesResolver(db_client),
        )

        change_log_ids = updater.update_search(search_id)

        assert len(change_log_ids) == 1
        change_log = find_model(session, db_models.ChangeLog, id=change_log_ids[0])
        assert change_log.change_type == ChangeType.topic_status_change
        assert change_log.new_value == 'Ищем'

        updated_search = find_model(session, db_models.Search, search_forum_num=search_id)
        assert updated_search.status == 'Ищем'
        assert updated_search.forum_folder_id == ACTIVE_FOLDER_ID

    @pytest.mark.parametrize('terminal_status', ['НЖ', 'НП', 'Найден'])
    def test_move_to_finished_folder_preserves_exact_terminal_status_without_extra_changelog(
        self,
        session: Session,
        db_client: DBClient,
        terminal_status: str,
    ) -> None:
        search_id = 793010 + ['НЖ', 'НП', 'Найден'].index(terminal_status)
        terminal_title = f'{terminal_status} Иванов Иван Иванович, 35 лет, г. Екатеринбург'
        db_factories.SearchFactory.create_sync(
            search_forum_num=search_id,
            forum_search_title=terminal_title,
            forum_folder_id=ACTIVE_FOLDER_ID,
            status=terminal_status,
            topic_type='search',
            topic_type_id=TopicType.search_regular,
            num_of_replies=5,
        )

        moved_item = ForumSearchItemFactory.build(
            search_id=search_id,
            title=terminal_title,
            folder_id=FINISHED_FOLDER_ID,
            replies_count=5,
        )
        updater = SearchUpdater(
            db_client,
            _SingleItemForum(moved_item),
            search_parser=SearchParser(CoordinatesResolver(db_client)),
            change_detector=ChangeDetector(),
            coordinates_resolver=CoordinatesResolver(db_client),
        )

        change_log_ids = updater.update_search(search_id)

        assert change_log_ids == []
        updated_search = find_model(session, db_models.Search, search_forum_num=search_id)
        assert updated_search.status == terminal_status
        assert updated_search.forum_folder_id == FINISHED_FOLDER_ID

    def test_legacy_folder_updater_marks_moved_search_as_finished(
        self,
        session: Session,
        connection_pool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        search_id = 793020
        db_factories.SearchFactory.create_sync(
            search_forum_num=search_id,
            forum_search_title=NEUTRAL_SEARCH_TITLE,
            forum_folder_id=ACTIVE_FOLDER_ID,
            status='Ищем',
            topic_type='search',
            topic_type_id=TopicType.search_regular,
            num_of_replies=1,
        )
        monkeypatch.setattr(
            legacy_folder_updater,
            'recognize_title_via_api',
            lambda title, status_only=False: _reco_payload(topic_type='search', status='Ищем'),
        )
        monkeypatch.setattr(FolderUpdater, '_update_coordinates', lambda *args, **kwargs: None)

        legacy_db = legacy_database.DBClient(connection_pool)
        forum = _LegacyListForum(
            [
                LegacyForumSearchItem(
                    title=NEUTRAL_SEARCH_TITLE,
                    search_id=search_id,
                    replies_count=1,
                    start_datetime=PARSED_TIME,
                )
            ]
        )
        updater = FolderUpdater(legacy_db, forum, FINISHED_FOLDER_ID)

        updated, change_log_ids = updater.run()

        assert updated is True
        assert len(change_log_ids) == 1
        change_log = find_model(session, db_models.ChangeLog, id=change_log_ids[0])
        assert change_log.change_type == ChangeType.topic_status_change
        assert change_log.new_value == 'Завершен'

        updated_search = find_model(session, db_models.Search, search_forum_num=search_id)
        assert updated_search.status == 'Завершен'
        assert updated_search.forum_folder_id == FINISHED_FOLDER_ID
