from faker import Faker
from polyfactory import Use
from polyfactory.factories import DataclassFactory

from identify_updates_of_topics._utils.topics_commons import ChangeLogLine, ForumCommentItem, SearchSummary

fake = Faker()


class SearchSummaryFactory(DataclassFactory[SearchSummary]):
    pass


class ChangeLogLineFactory(DataclassFactory[ChangeLogLine]):
    pass


class ForumCommentItemFactory(DataclassFactory[ForumCommentItem]):
    comment_forum_global_id = Use(fake.pystr, max_chars=10)
