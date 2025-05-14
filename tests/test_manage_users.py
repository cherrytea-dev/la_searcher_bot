from datetime import datetime
from random import randint
from unittest.mock import MagicMock, patch

import pytest

import _dependencies.pubsub
from manage_users import main
from tests.common import get_event_with_data
from tests.factories.db_factories import UserFactory, UserOnboardingFactory, UserStatusesHistoryFactory, get_session
from tests.factories.db_models import User, UserOnboarding, UserPreference, UserStatusesHistory


@pytest.fixture
def user_id() -> int:
    return randint(1, 1_000_000)


class TestMain:
    def test_main_block_user(self):
        data = {
            'action': 'block_user',
            'info': {'user': 123456},
            'time': '2023-05-20 10:00:00.000000',
        }
        mock_event = get_event_with_data(data)

        with patch('manage_users.main.save_updated_status_for_user') as mock_save:
            result = main.main(mock_event, '')

            mock_save.assert_called_once_with('block_user', 123456, datetime(2023, 5, 20, 10, 0))
            assert result == 'ok'

    def test_main_unblock_user(self):
        data = {
            'action': 'unblock_user',
            'info': {'user': 789012},
            'time': '2023-06-15 14:30:00.000000',
        }
        mock_event = get_event_with_data(data)

        with patch('manage_users.main.save_updated_status_for_user') as mock_save:
            result = main.main(mock_event, '')

            mock_save.assert_called_once_with('unblock_user', 789012, datetime(2023, 6, 15, 14, 30))
            assert result == 'ok'

    def test_main_new_user(self):
        data = {
            'action': 'new',
            'info': {'user': 987654, 'username': 'test_user'},
            'time': '2023-07-10 09:00:00.000000',
        }
        mock_event = get_event_with_data(data)

        with (
            patch('manage_users.main.save_updated_status_for_user') as mock_save_status,
            patch('manage_users.main.save_new_user') as mock_save_new,
            patch('manage_users.main.save_default_notif_settings') as mock_save_notif,
        ):
            result = main.main(mock_event, '')

            mock_save_status.assert_called_once_with('new', 987654, datetime(2023, 7, 10, 9, 0))
            mock_save_new.assert_called_once_with(987654, 'test_user', datetime(2023, 7, 10, 9, 0))
            mock_save_notif.assert_called_once_with(987654)
            assert result == 'ok'

    def test_main_delete_user(self):
        data = {
            'action': 'delete_user',
            'info': {'user': 555555},
            'time': '2023-08-20 12:00:00.000000',
        }
        mock_event = get_event_with_data(data)

        with patch('manage_users.main.save_updated_status_for_user') as mock_save:
            result = main.main(mock_event, '')

            mock_save.assert_called_once_with('delete_user', 555555, datetime(2023, 8, 20, 12, 0))
            assert result == 'ok'

    def test_main_update_onboarding(self):
        data = {
            'action': 'update_onboarding',
            'info': {'user': 555555},
            'time': '2023-08-20 12:00:00.000000',
            'step': 'foo',
        }
        mock_event = get_event_with_data(data)

        with patch('manage_users.main.save_onboarding_step') as mock_save_onboarding_step:
            result = main.main(mock_event, '')

            mock_save_onboarding_step.assert_called_once_with(555555, 'foo', datetime(2023, 8, 20, 12, 0))
            assert result == 'ok'


class TestSaveUpdatedStatusForUser:
    def test_block_user(self, user_id: int):
        user = UserFactory.create_sync(user_id=user_id, status='active')
        timestamp = datetime.now()

        main.save_updated_status_for_user(_dependencies.pubsub.ManageUserAction.block_user, user_id, timestamp)

        updated_user: User = get_session().query(User).filter_by(user_id=user_id).first()
        assert updated_user.status == 'blocked'
        assert updated_user.status_change_date == timestamp

        status_history: UserStatusesHistory = (
            get_session().query(UserStatusesHistory).filter_by(user_id=user_id).first()
        )
        assert status_history.status == 'blocked'
        assert status_history.date == timestamp

    def test_unblock_user(self, user_id: int):
        user = UserFactory.create_sync(user_id=user_id, status='blocked')
        timestamp = datetime.now()

        main.save_updated_status_for_user(_dependencies.pubsub.ManageUserAction.unblock_user, user_id, timestamp)

        updated_user: User = get_session().query(User).filter_by(user_id=user_id).first()
        assert updated_user.status == 'unblocked'
        assert updated_user.status_change_date == timestamp

        status_history: UserStatusesHistory = (
            get_session().query(UserStatusesHistory).filter_by(user_id=user_id).first()
        )
        assert status_history.status == 'unblocked'
        assert status_history.date == timestamp

    def test_new_user(self, user_id: int):
        timestamp = datetime.now()

        main.save_updated_status_for_user(_dependencies.pubsub.ManageUserAction.new, user_id, timestamp)

        user: User = get_session().query(User).filter_by(user_id=user_id).first()
        assert user is None  # 'new' action doesn't update the users table

        status_history: UserStatusesHistory = (
            get_session().query(UserStatusesHistory).filter_by(user_id=user_id).first()
        )
        assert status_history.status == 'new'
        assert status_history.date == timestamp


class TestSaveOnboardingStep:
    def test_save_valid_onboarding_step(self, user_id: int):
        # user_id = 12345
        step_name = 'role_set'
        timestamp = datetime.now()

        main.save_onboarding_step(user_id, step_name, timestamp)

        saved_step: UserOnboarding = get_session().query(UserOnboarding).filter_by(user_id=user_id).first()
        assert saved_step is not None
        assert saved_step.step_id == 10
        assert saved_step.step_name == step_name
        # assert saved_step.timestamp == timestamp

    def test_save_unrecognized_step(self, user_id: int):
        step_name = 'unknown_step'
        timestamp = datetime.now()

        main.save_onboarding_step(user_id, step_name, timestamp)

        saved_step: UserOnboarding = get_session().query(UserOnboarding).filter_by(user_id=user_id).first()
        assert saved_step is not None
        assert saved_step.step_id == 99
        assert saved_step.step_name == step_name
        # assert saved_step.timestamp == timestamp

    def test_save_multiple_steps_for_same_user(self, user_id: int):
        steps = [
            ('start', datetime.now()),
            ('role_set', datetime.now()),
            ('moscow_replied', datetime.now()),
        ]

        for step_name, timestamp in steps:
            main.save_onboarding_step(user_id, step_name, timestamp)

        saved_steps: list[UserOnboarding] = list(get_session().query(UserOnboarding).filter_by(user_id=user_id).all())
        assert len(saved_steps) == 3

        for i, (step_name, timestamp) in enumerate(steps):
            assert saved_steps[i].step_name == step_name
            assert saved_steps[i].timestamp == timestamp


class TestSaveNewUser:
    def test_save_new_user_success(self, user_id: int):
        username = 'test_user'
        timestamp = datetime.now()

        main.save_new_user(user_id, username, timestamp)

        user: User = get_session().query(User).filter_by(user_id=user_id).first()
        assert user is not None
        assert user.user_id == user_id
        assert user.username_telegram == username
        assert user.reg_date == timestamp

        onboarding: UserOnboarding = get_session().query(UserOnboarding).filter_by(user_id=user_id).first()
        assert onboarding is not None
        assert onboarding.step_id == 0
        assert onboarding.step_name == 'start'

    def test_save_new_user_unknown_username(self, user_id: int):
        username = 'unknown'
        timestamp = datetime.now()

        main.save_new_user(user_id, username, timestamp)

        user: User = get_session().query(User).filter_by(user_id=user_id).first()
        assert user is not None
        assert user.user_id == user_id
        assert user.username_telegram is None
        assert user.reg_date == timestamp

    def test_save_new_user_duplicate(self, user_id: int):
        username = 'existing_user'
        timestamp = datetime.now()

        # Create an existing user
        UserFactory.create_sync(user_id=user_id, username_telegram=username, reg_date=timestamp)

        # Try to save the same user again
        main.save_new_user(user_id, username, timestamp)

        # Check that no new user was created
        users: list[User] = list(get_session().query(User).filter_by(user_id=user_id).all())
        assert len(users) == 1
        assert users[0].username_telegram == username
        assert users[0].reg_date == timestamp

        # Check that onboarding entry was still created
        onboarding: UserOnboarding = get_session().query(UserOnboarding).filter_by(user_id=user_id).first()
        assert onboarding is not None
        assert onboarding.step_id == 0
        assert onboarding.step_name == 'start'


class TestSaveDefaultNotifSettings:
    def test_save_default_notif_settings(self, user_id: int):
        main.save_default_notif_settings(user_id)

        user_pref_bot_news: UserPreference = (
            get_session().query(UserPreference).filter_by(user_id=user_id, preference='bot_news').first()
        )
        assert user_pref_bot_news is not None
        assert user_pref_bot_news.pref_id == 20
