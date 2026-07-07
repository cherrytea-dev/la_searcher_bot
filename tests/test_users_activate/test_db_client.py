import datetime

from sqlalchemy.orm import Session

from tests.factories import db_factories, db_models
from users_activate._utils.database import DBClient


class TestInsertOnboardingStep:
    def test_creates_onboarding_record(self, db_client: DBClient, session: Session) -> None:
        user = db_factories.UserFactory.create_sync()

        db_client.insert_onboarding_step(user.user_id, 'start', 0)

        record = (
            session.query(db_models.UserOnboarding)
            .filter_by(user_id=user.user_id, step_name='start', step_id=0)
            .one_or_none()
        )
        assert record is not None
        assert record.user_id == user.user_id
        assert record.step_name == 'start'
        assert record.step_id == 0


class TestGetUserForOnboardingStep0:
    def test_returns_user_when_eligible(self, db_client: DBClient) -> None:
        """User with reg_date before cutoff, no onboarding, last msg = /start."""
        user = db_factories.UserFactory.create_sync(
            reg_date=datetime.datetime(2023, 1, 1),
            role=None,
        )
        db_factories.DialogFactory.create_sync(
            user_id=user.user_id,
            author='user',
            message_text='/start',
            timestamp=datetime.datetime(2023, 6, 1),
        )

        result = db_client.get_user_for_onboarding_step_0()

        assert result == user.user_id

    def test_returns_none_when_no_eligible_user(self, db_client: DBClient) -> None:
        result = db_client.get_user_for_onboarding_step_0()

        assert result is None


class TestGetUserForOnboardingStep02:
    def test_returns_user_when_eligible(self, db_client: DBClient) -> None:
        """No role, no folder setting, no onboarding."""
        user = db_factories.UserFactory.create_sync(role=None)

        result = db_client.get_user_for_onboarding_step_0_2()

        assert result == user.user_id

    def test_returns_none_when_user_has_onboarding(self, db_client: DBClient) -> None:
        user = db_factories.UserFactory.create_sync(role=None)
        db_factories.UserOnboardingFactory.create_sync(user_id=user.user_id)

        result = db_client.get_user_for_onboarding_step_0_2()

        assert result is None

    def test_returns_none_when_user_has_folder_setting(self, db_client: DBClient) -> None:
        user = db_factories.UserFactory.create_sync(role=None)
        db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user.user_id)

        result = db_client.get_user_for_onboarding_step_0_2()

        assert result is None

    def test_returns_none_when_user_has_role(self, db_client: DBClient) -> None:
        db_factories.UserFactory.create_sync(role='coordinator')

        result = db_client.get_user_for_onboarding_step_0_2()

        assert result is None


class TestGetUserForOnboardingStep102:
    def test_returns_user_when_eligible(self, db_client: DBClient) -> None:
        """Has role, no folder setting, no onboarding."""
        user = db_factories.UserFactory.create_sync(
            role='coordinator',
        )

        result = db_client.get_user_for_onboarding_step_10_2()

        assert result == user.user_id

    def test_returns_none_when_no_folder_but_no_role(self, db_client: DBClient) -> None:
        db_factories.UserFactory.create_sync(role=None)

        result = db_client.get_user_for_onboarding_step_10_2()

        assert result is None

    def test_returns_none_when_has_onboarding(self, db_client: DBClient) -> None:
        user = db_factories.UserFactory.create_sync(role='coordinator')
        db_factories.UserOnboardingFactory.create_sync(user_id=user.user_id)

        result = db_client.get_user_for_onboarding_step_10_2()

        assert result is None

    def test_returns_none_when_has_folder_setting(self, db_client: DBClient) -> None:
        user = db_factories.UserFactory.create_sync(role='coordinator')
        db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user.user_id)

        result = db_client.get_user_for_onboarding_step_10_2()

        assert result is None
