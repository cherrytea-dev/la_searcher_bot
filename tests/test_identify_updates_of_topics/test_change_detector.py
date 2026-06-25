from copy import deepcopy

from _dependencies.common.commons import ChangeType
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
