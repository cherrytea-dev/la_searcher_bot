"""User repository — consolidated DB operations for all bots.

This package contains domain-specific mixins that were previously
duplicated across communicate/_utils/database.py and vk_bot/_utils/mixins/.
Each mixin is self-contained and uses self.connect() from DBClientBase.

The UserRepository class at the bottom combines all mixins into a single
interface used by both Telegram and VK bots.
"""

from _dependencies.common.db_client import DBClientBase

from .age_pref import AgePrefMixin
from .dialog_history import DialogHistoryMixin
from .dialog_state import DialogStateMixin
from .forum_attribute import ForumAttributeMixin
from .geo_pref import GeoPrefMixin
from .notification_pref import NotificationPrefMixin
from .region import RegionMixin
from .search_following import SearchFollowingMixin
from .settings_summary import SettingsSummaryMixin
from .system_role import SystemRoleMixin
from .topic_type import TopicTypeMixin
from .user import UserMixin
from .vk_identity import VKIdentityMixin


class UserRepository(
    DBClientBase,
    SystemRoleMixin,
    SearchFollowingMixin,
    GeoPrefMixin,
    AgePrefMixin,
    TopicTypeMixin,
    RegionMixin,
    NotificationPrefMixin,
    DialogStateMixin,
    DialogHistoryMixin,
    ForumAttributeMixin,
    UserMixin,
    SettingsSummaryMixin,
    VKIdentityMixin,
):
    """Единый репозиторий пользовательских данных для всех ботов.

    All mixins use self.connect() from DBClientBase.
    """
