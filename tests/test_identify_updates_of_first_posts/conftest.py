import pytest

from identify_updates_of_first_posts._utils.database import DBClient


@pytest.fixture
def db_client(connection_pool) -> DBClient:
    return DBClient(connection_pool)
