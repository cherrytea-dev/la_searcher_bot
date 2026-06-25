"""VK bot DB client composed from domain-specific mixins.

Previously this module contained both VK-specific methods and a `.settings`
property that returned a separate UserSettingsService (another DBClientBase).
Now all DB operations are mixed into a single DBClient class.
"""

from functools import lru_cache

from _dependencies.common.db_client import DBClientBase

from .database_common import AgePeriod, DialogState, UserSettingsSummary
from .mixins.age_pref import AgePrefMixin
from .mixins.dialog_history import DialogHistoryMixin
from .mixins.dialog_state import DialogStateMixin
from .mixins.forum_attribute import ForumAttributeMixin
from .mixins.geo_pref import GeoPrefMixin
from .mixins.notification_pref import NotificationPrefMixin
from .mixins.region import RegionMixin
from .mixins.search_following import SearchFollowingMixin
from .mixins.settings_summary import SettingsSummaryMixin
from .mixins.system_role import SystemRoleMixin
from .mixins.topic_type import TopicTypeMixin
from .mixins.user import UserMixin
from .mixins.vk_identity import VKIdentityMixin


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
    """VK bot DB client composed from domain-specific mixins.

    All mixins use self.connect() from DBClientBase.
    No more ``.settings`` property — all methods are available directly.
    """


@lru_cache
def db() -> DBClient:
    return DBClient()
