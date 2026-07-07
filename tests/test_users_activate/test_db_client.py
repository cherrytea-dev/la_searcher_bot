from sqlalchemy.orm import Session

from tests.factories import db_factories, db_models
from users_activate._utils.database import DBClient


class TestInsertOnboardingStep:
    def test_creates_onboarding_record(self, db_client: DBClient, session: Session) -> None:
        """Insert a row and verify it exists via ORM — unique enough to not collide under xdist."""
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
    def test_smoke(self, db_client: DBClient) -> None:
        """Smoke — just verify the SQL doesn't crash under parallel xdist."""
        db_client.get_user_for_onboarding_step_0()
        # no crash = success


class TestGetUserForOnboardingStep02:
    def test_smoke(self, db_client: DBClient) -> None:
        """Smoke — just verify the SQL doesn't crash under parallel xdist."""
        db_client.get_user_for_onboarding_step_0_2()
        # no crash = success


class TestGetUserForOnboardingStep102:
    def test_smoke(self, db_client: DBClient) -> None:
        """Smoke — just verify the SQL doesn't crash under parallel xdist."""
        db_client.get_user_for_onboarding_step_10_2()
        # no crash = success
