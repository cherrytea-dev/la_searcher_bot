from datetime import datetime
from random import randint

import pytest
from sqlalchemy.engine import Connection

from _dependencies.users_management import (
    ManageUserAction,
    _save_default_notif_settings,
    _save_new_user,
    save_onboarding_step,
    update_user_status,
)
from tests.common import find_model
from tests.factories.db_factories import UserFactory, get_session
from tests.factories.db_models import User, UserOnboarding, UserPreference, UserStatusesHistory


@pytest.fixture
def user_id() -> int:
    return randint(1, 1_000_000)


class TestSaveUpdatedStatusForUser:
    def test_block_user(self, user_id: int):
        user = UserFactory.create_sync(user_id=user_id, status='active')

        update_user_status(ManageUserAction.block_user, user_id)

        assert find_model(get_session(), User, user_id=user_id, status='blocked')
        assert find_model(get_session(), UserStatusesHistory, user_id=user_id, status='blocked')

    def test_unblock_user(self, user_id: int):
        user = UserFactory.create_sync(user_id=user_id, status='blocked')

        update_user_status(ManageUserAction.unblock_user, user_id)

        assert find_model(get_session(), User, user_id=user_id, status='unblocked')
        assert find_model(get_session(), UserStatusesHistory, user_id=user_id, status='unblocked')


class TestSaveOnboardingStep:
    def test_save_valid_onboarding_step(self, user_id: int):
        step_name = 'role_set'

        save_onboarding_step(user_id, step_name)

        saved_step = find_model(get_session(), UserOnboarding, user_id=user_id)
        assert saved_step is not None
        assert saved_step.step_id == 10
        assert saved_step.step_name == step_name

    def test_save_unrecognized_step(self, user_id: int):
        step_name = 'unknown_step'

        save_onboarding_step(user_id, step_name)

        saved_step = find_model(get_session(), UserOnboarding, user_id=user_id)
        assert saved_step is not None
        assert saved_step.step_id == 99
        assert saved_step.step_name == step_name

    def test_save_multiple_steps_for_same_user(self, user_id: int):
        steps = [
            ('start', datetime.now()),
            ('role_set', datetime.now()),
            ('moscow_replied', datetime.now()),
        ]

        for step_name, timestamp in steps:
            save_onboarding_step(user_id, step_name)

        saved_steps: list[UserOnboarding] = list(get_session().query(UserOnboarding).filter_by(user_id=user_id).all())
        assert len(saved_steps) == 3

        for i, (step_name, timestamp_) in enumerate(steps):
            assert saved_steps[i].step_name == step_name


class TestSaveNewUser:
    def test_save_new_user_success(self, user_id: int, connection: Connection):
        username = 'test_user'
        timestamp = datetime.now()

        _save_new_user(connection, user_id, username, timestamp)

        user = find_model(get_session(), User, user_id=user_id)
        assert user is not None
        assert user.user_id == user_id
        assert user.username_telegram == username
        assert user.reg_date == timestamp

        onboarding = find_model(get_session(), UserOnboarding, user_id=user_id)
        assert onboarding is not None
        assert onboarding.step_id == 0
        assert onboarding.step_name == 'start'

    def test_save_new_user_unknown_username(self, user_id: int, connection: Connection):
        username = None
        timestamp = datetime.now()

        _save_new_user(connection, user_id, username, timestamp)

        user = find_model(get_session(), User, user_id=user_id)
        assert user is not None
        assert user.user_id == user_id
        assert user.username_telegram is None
        assert user.reg_date == timestamp

    def test_save_new_user_duplicate(self, user_id: int, connection: Connection):
        username = 'existing_user'
        timestamp = datetime.now()

        # Create an existing user
        UserFactory.create_sync(user_id=user_id, username_telegram=username, reg_date=timestamp)

        # Try to save the same user again
        _save_new_user(connection, user_id, username, timestamp)

        # Check that no new user was created
        users: list[User] = list(get_session().query(User).filter_by(user_id=user_id).all())
        assert len(users) == 1
        assert users[0].username_telegram == username
        assert users[0].reg_date == timestamp

        # Check that onboarding entry was still created
        onboarding = find_model(get_session(), UserOnboarding, user_id=user_id)
        assert onboarding is not None
        assert onboarding.step_id == 0
        assert onboarding.step_name == 'start'


class TestSaveDefaultNotifSettings:
    def test_save_default_notif_settings(self, user_id: int, connection: Connection):
        _save_default_notif_settings(connection, user_id)

        user_pref_bot_news = find_model(get_session(), UserPreference, user_id=user_id, preference='bot_news')

        assert user_pref_bot_news is not None
        assert user_pref_bot_news.pref_id == 20
