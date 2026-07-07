import pytest
from sqlalchemy.engine import Engine

from users_activate._utils.database import DBClient


@pytest.fixture
def db_client(connection_pool: Engine) -> DBClient:
    return DBClient(db=connection_pool)
