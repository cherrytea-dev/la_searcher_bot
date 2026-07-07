import pytest
import sqlalchemy
from sqlalchemy.engine import Engine

from users_activate._utils.database import DBClient


@pytest.fixture
def db_client(connection_pool: Engine) -> DBClient:
    return DBClient(db=connection_pool)


@pytest.fixture(autouse=True)
def _clean_users_tables(connection_pool: Engine) -> None:
    """Clean up data between tests — these queries use LIMIT 1 so stale data breaks assertions."""
    yield
    with connection_pool.begin() as conn:
        conn.execute(
            sqlalchemy.text("""
                TRUNCATE
                    users,
                    user_onboarding,
                    user_regional_preferences,
                    dialogs
                CASCADE
            """)
        )
