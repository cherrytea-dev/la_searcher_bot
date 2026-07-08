"""DB client for compose_notifications — collects all SQL mixins into DBClient."""

from _dependencies.common.db_client import DBClientBase

from ._mixins.changelog_mixin import ChangeLogMixin
from ._mixins.comments_mixin import CommentsMixin
from ._mixins.notification_record_mixin import NotificationRecordMixin
from ._mixins.notification_stats_mixin import NotificationStatsMixin
from ._mixins.search_info_mixin import SearchInfoMixin
from ._mixins.user_filter_mixin import UserFilterMixin


class DBClient(
    DBClientBase,
    ChangeLogMixin,
    SearchInfoMixin,
    CommentsMixin,
    UserFilterMixin,
    NotificationRecordMixin,
    NotificationStatsMixin,
):
    """DB client for compose_notifications.

    Combines all domain-specific mixins into a single class.
    """
