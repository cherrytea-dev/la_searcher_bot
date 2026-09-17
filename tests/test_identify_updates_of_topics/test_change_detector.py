from copy import deepcopy
from datetime import datetime

from _dependencies.common.commons import ChangeType
from identify_updates_of_topics._legacy._utils.folder_updater import changes_digest as legacy_changes_digest
from identify_updates_of_topics._legacy._utils.topics_commons import ChangeLogLine as LegacyChangeLogLine
from identify_updates_of_topics._utils.change_detector import ChangeDetector
from tests.test_identify_updates_of_topics.factories import SearchSummaryFactory


class TestChangeDetector:
    """Standalone pure unit tests for ChangeDetector — no DB, no forum, no fixtures needed."""

    def setup_method(self):
        self.detector = ChangeDetector()

    def test_no_changes(self):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)

        changes = self.detector.detect(snapshot, search, False)

        assert not changes

    def test_changed_title(self):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)
        search.title = 'New Title'

        changes = self.detector.detect(snapshot, search, False)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.topic_title_change

    def test_changed_status(self):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)
        search.status = 'New Status'

        changes = self.detector.detect(snapshot, search, False)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.topic_status_change

    def test_changed_num_of_replies_no_inforg(self):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)
        search.num_of_replies -= 1

        changes = self.detector.detect(snapshot, search, False)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.topic_comment_new

    def test_changed_num_of_replies_inforg(self):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)
        search.num_of_replies -= 1

        changes = self.detector.detect(snapshot, search, True)

        assert len(changes) == 2
        assert changes[0].change_type == ChangeType.topic_comment_new
        assert changes[1].change_type == ChangeType.topic_inforg_comment_new

    def test_multiple_changes(self):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)
        search.title = 'Different Title'
        search.status = 'Different Status'
        search.num_of_replies -= 1

        changes = self.detector.detect(snapshot, search, True)

        assert len(changes) == 4
        change_types = [c.change_type for c in changes]
        assert ChangeType.topic_status_change in change_types
        assert ChangeType.topic_title_change in change_types
        assert ChangeType.topic_comment_new in change_types
        assert ChangeType.topic_inforg_comment_new in change_types


class TestChangeDetectorLogging:
    """Regression: INFO carries a compact digest, the whole SearchSummary dump lives in DEBUG."""

    def test_logs_digest_instead_of_full_dump(self, caplog):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)
        search.status = 'СТОП'

        with caplog.at_level('INFO'):
            changes = ChangeDetector.detect(snapshot, search, False)

        messages = [record.getMessage() for record in caplog.records]
        digest = [message for message in messages if 'changes for search' in message]

        assert digest, messages
        assert 'status_change' in digest[0]
        assert len(changes) == 1

    def test_full_summaries_are_not_dumped_on_info(self, caplog):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)
        search.status = 'СТОП'

        with caplog.at_level('INFO'):
            ChangeDetector.detect(snapshot, search, False)

        messages = [record.getMessage() for record in caplog.records]

        assert not [message for message in messages if 'Comparing changes' in message]
        assert not [message for message in messages if 'SearchSummary(' in message]

    def test_nothing_is_logged_when_there_are_no_changes(self, caplog):
        snapshot = SearchSummaryFactory.build()
        search = deepcopy(snapshot)

        with caplog.at_level('INFO'):
            ChangeDetector.detect(snapshot, search, False)

        messages = [record.getMessage() for record in caplog.records]

        assert not [message for message in messages if 'changes for search' in message]

    def test_long_value_is_logged_as_length_and_fingerprint(self, caplog):
        snapshot = SearchSummaryFactory.build()
        snapshot.title = 'Пропала ' + 'очень длинный заголовок ' * 10
        search = deepcopy(snapshot)
        search.title = 'Короткое'

        with caplog.at_level('INFO'):
            ChangeDetector.detect(snapshot, search, False)

        digest = [record.getMessage() for record in caplog.records if 'changes for search' in record.getMessage()]

        assert digest, [record.getMessage() for record in caplog.records]
        assert 'title_change' in digest[0]
        assert 'chars' in digest[0]
        assert 'fingerprint' in digest[0]
        assert search.title not in digest[0]


class TestLegacyChangesDigest:
    """The legacy folder_updater (the one running in prod) logs the same compact digest."""

    @staticmethod
    def _line(new_value, changed_field: str = 'status_change'):
        return LegacyChangeLogLine(
            parsed_time=datetime.now(),
            topic_id=555,
            new_value=new_value,
            changed_field=changed_field,
            parameters='',
            change_type=ChangeType.topic_status_change,
        )

    def test_short_value_is_logged_as_is(self):
        assert legacy_changes_digest([self._line('СТОП')]) == 'changes for search 555: 1 — status_change=СТОП'

    def test_long_value_is_logged_as_length_and_fingerprint(self):
        long_title = 'Пропала ' + 'очень длинный заголовок ' * 10

        digest = legacy_changes_digest([self._line(long_title, changed_field='title_change')])

        assert 'title_change=Пропала' in digest
        assert f'({len(long_title)} chars, fingerprint ' in digest
        assert long_title not in digest
