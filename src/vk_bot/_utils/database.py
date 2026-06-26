"""VK bot DB client composed from consolidated domain-specific mixins.

All mixins are now imported from ``_dependencies.user_repository``.
The local mixin files in ``mixins/`` are kept for backward compatibility
during the transition period and will be removed in a future cleanup.
"""

from functools import lru_cache

from _dependencies.common.db_client import DBClientBase
from _dependencies.user_repository import (
    AgePrefMixin,
    DialogHistoryMixin,
    DialogStateMixin,
    ForumAttributeMixin,
    GeoPrefMixin,
    NotificationPrefMixin,
    RegionMixin,
    SearchFollowingMixin,
    SettingsSummaryMixin,
    SystemRoleMixin,
    TopicTypeMixin,
    UserMixin,
    VKIdentityMixin,
)


class DBClient(
    DBClientBase,
    VKIdentityMixin,
    DialogStateMixin,
    UserMixin,
    RegionMixin,
    NotificationPrefMixin,
    GeoPrefMixin,
    AgePrefMixin,
    TopicTypeMixin,
    SearchFollowingMixin,
    ForumAttributeMixin,
    SystemRoleMixin,
    DialogHistoryMixin,
    SettingsSummaryMixin,
):
    """VK bot DB client composed from consolidated domain-specific mixins.

    All mixins use self.connect() from DBClientBase.
    """


@lru_cache
def db() -> DBClient:
    return DBClient()
