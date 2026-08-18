"""Tests for resetting user settings to registration defaults.

Covers the shared ``SettingsResetMixin`` exposed via ``UserRepository``:
- wipes all per-user preference tables
- re-seeds default notification prefs and default topic types (registration state)
- restores subscription (unsubscribed → unblocked)
- rolls onboarding back to region selection
- is idempotent
- leaves identity/delivery untouched (role, system roles, forum link, blocked status)
"""

from random import randint

import sqlalchemy
import pytest

from _dependencies.user_repository import UserRepository

DEFAULT_PREFS = {'new_searches', 'status_changes', 'inforg_comments', 'first_post_changes', 'bot_news'}
# Registration seeds topic types with role=None → [0, 4, 5], regardless of the
# user's actual role (role-aware [0,3,4,5] is only applied during onboarding).
REGISTRATION_TOPIC_TYPES = {0, 4, 5}


@pytest.fixture
def user_id() -> int:
    return randint(1_000_000_000, 9_000_000_000)


@pytest.fixture
def repo() -> UserRepository:
    return UserRepository()


@pytest.fixture
def pool(connection_pool):
    return connection_pool


def _seed_user_with_full_settings(pool, user_id: int, role: str = 'member') -> None:
    """Create a user and populate every preference table with non-default data."""
    with pool.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO users (user_id, internal_user_id, role) "
                "VALUES (:uid, :iid, :role) ON CONFLICT (user_id) DO UPDATE SET role=:role"
            ),
            {'uid': user_id, 'iid': user_id, 'role': role},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_preferences (user_id, preference, pref_id) VALUES (:u, 'comments_changes', 3)"),
            {'u': user_id},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_pref_age (user_id, period_min, period_max) VALUES (:u, 0, 10)"),
            {'u': user_id},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_pref_topic_type (user_id, topic_type_id) VALUES (:u, 1)"),
            {'u': user_id},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_pref_radius (user_id, radius) VALUES (:u, 150)"),
            {'u': user_id},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_coordinates (user_id, latitude, longitude) VALUES (:u, '55.7', '37.6')"),
            {'u': user_id},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_regional_preferences (user_id, forum_folder_num) VALUES (:u, 42)"),
            {'u': user_id},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_pref_region (user_id, region_id) VALUES (:u, 42)"),
            {'u': user_id},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_pref_search_whitelist (user_id, search_id) VALUES (:u, 123)"),
            {'u': user_id},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_forum_attributes (user_id, forum_username, status) VALUES (:u, 'nick', 'verified')"),
            {'u': user_id},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_roles (user_id, role) VALUES (:u, 'tester')"),
            {'u': user_id},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_onboarding (user_id, step_id, step_name) VALUES (:u, 0, 'start')"),
            {'u': user_id},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_onboarding (user_id, step_id, step_name) VALUES (:u, 10, 'role_set')"),
            {'u': user_id},
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO user_onboarding (user_id, step_id, step_name) VALUES (:u, 80, 'finished')"),
            {'u': user_id},
        )


def _count(pool, table: str, user_id: int) -> int:
    with pool.begin() as conn:
        return conn.execute(
            sqlalchemy.text(f'SELECT count(*) FROM {table} WHERE user_id=:u'), {'u': user_id}
        ).scalar()


def _pref_names(pool, user_id: int) -> set[str]:
    with pool.begin() as conn:
        rows = conn.execute(
            sqlalchemy.text('SELECT preference FROM user_preferences WHERE user_id=:u'), {'u': user_id}
        ).fetchall()
        return {r[0] for r in rows}


def _topic_type_ids(pool, user_id: int) -> set[int]:
    with pool.begin() as conn:
        rows = conn.execute(
            sqlalchemy.text('SELECT topic_type_id FROM user_pref_topic_type WHERE user_id=:u'), {'u': user_id}
        ).fetchall()
        return {r[0] for r in rows}


def _user_role(pool, user_id: int) -> str | None:
    with pool.begin() as conn:
        return conn.execute(
            sqlalchemy.text('SELECT role FROM users WHERE user_id=:u'), {'u': user_id}
        ).scalar()


def _user_status(pool, user_id: int) -> str | None:
    with pool.begin() as conn:
        return conn.execute(
            sqlalchemy.text('SELECT status FROM users WHERE user_id=:u'), {'u': user_id}
        ).scalar()


def _max_onboarding_step(pool, user_id: int) -> int | None:
    with pool.begin() as conn:
        return conn.execute(
            sqlalchemy.text('SELECT MAX(step_id) FROM user_onboarding WHERE user_id=:u'), {'u': user_id}
        ).scalar()


class TestResetUserSettings:
    def test_reset_wipes_preferences_and_reseeds_defaults(self, pool, repo, user_id: int):
        _seed_user_with_full_settings(pool, user_id, role='member')

        repo.reset_user_settings(user_id)

        # notification prefs → exactly the 5 defaults
        assert _pref_names(pool, user_id) == DEFAULT_PREFS
        # topic types → registration default (role=None), NOT role-aware onboarding set
        assert _topic_type_ids(pool, user_id) == REGISTRATION_TOPIC_TYPES
        # everything else wiped
        for table in (
            'user_pref_age',
            'user_pref_radius',
            'user_coordinates',
            'user_regional_preferences',
            'user_pref_region',
            'user_pref_search_filtering',
            'user_pref_search_whitelist',
        ):
            assert _count(pool, table, user_id) == 0, f'{table} not wiped'

    def test_reset_is_registration_state_for_any_role(self, pool, repo, user_id: int):
        """Even a member gets registration topic types [0,4,5], not [0,3,4,5]."""
        _seed_user_with_full_settings(pool, user_id, role='member')

        repo.reset_user_settings(user_id)

        assert _topic_type_ids(pool, user_id) == {0, 4, 5}

    def test_reset_restores_subscription(self, pool, repo, user_id: int):
        _seed_user_with_full_settings(pool, user_id)
        with pool.begin() as conn:
            conn.execute(
                sqlalchemy.text("UPDATE users SET status='unsubscribed' WHERE user_id=:u"),
                {'u': user_id},
            )

        repo.reset_user_settings(user_id)

        assert _user_status(pool, user_id) == 'unblocked'

    def test_reset_does_not_unblock_admin_blocked_user(self, pool, repo, user_id: int):
        _seed_user_with_full_settings(pool, user_id)
        with pool.begin() as conn:
            conn.execute(
                sqlalchemy.text("UPDATE users SET status='blocked' WHERE user_id=:u"),
                {'u': user_id},
            )

        repo.reset_user_settings(user_id)

        assert _user_status(pool, user_id) == 'blocked'

    def test_reset_rolls_onboarding_back_to_region_selection(self, pool, repo, user_id: int):
        _seed_user_with_full_settings(pool, user_id)

        repo.reset_user_settings(user_id)

        # finished(80) removed; max step should now be role_set(10)
        assert _max_onboarding_step(pool, user_id) == 10

    def test_reset_preserves_identity(self, pool, repo, user_id: int):
        _seed_user_with_full_settings(pool, user_id, role='member')

        repo.reset_user_settings(user_id)

        # role untouched
        assert _user_role(pool, user_id) == 'member'
        # system roles untouched
        assert _count(pool, 'user_roles', user_id) == 1
        # forum link untouched
        assert _count(pool, 'user_forum_attributes', user_id) == 1

    def test_reset_is_idempotent(self, pool, repo, user_id: int):
        _seed_user_with_full_settings(pool, user_id, role='member')

        repo.reset_user_settings(user_id)
        repo.reset_user_settings(user_id)

        assert _pref_names(pool, user_id) == DEFAULT_PREFS
        assert _topic_type_ids(pool, user_id) == REGISTRATION_TOPIC_TYPES
        assert _max_onboarding_step(pool, user_id) == 10
