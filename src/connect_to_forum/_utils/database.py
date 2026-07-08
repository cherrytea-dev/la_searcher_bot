"""DB client for connect_to_forum — delegates to shared UserRepository mixins."""

from _dependencies.common.db_client import DBClientBase
from _dependencies.user_repository.dialog_history import DialogHistoryMixin
from _dependencies.user_repository.dialog_state import DialogStateMixin
from _dependencies.user_repository.forum_attribute import ForumAttributeMixin
from _dependencies.user_repository.region import RegionMixin


class DBClient(
    DBClientBase,
    ForumAttributeMixin,
    RegionMixin,
    DialogStateMixin,
    DialogHistoryMixin,
):
    """DB client for connect_to_forum.

    Composed from shared UserRepository mixins to avoid code duplication.
    """
