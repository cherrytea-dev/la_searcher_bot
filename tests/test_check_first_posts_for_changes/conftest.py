from uuid import uuid4

import pytest
from sqlalchemy import text

from _dependencies.forum import recognition_cache


@pytest.fixture(autouse=True)
def isolated_recognition_cache(monkeypatch, connection_pool):
    """Give every test its own recognition cache namespace.

    The cache lives in the shared test database (`key_value_storage`), so without this a title
    recognized in one test would be reused in another one — and a test asserting that the title
    went to the API would fail depending on the order of the run.
    """

    prefix = f'test-reco-{uuid4().hex[:12]}'
    monkeypatch.setattr(recognition_cache, 'CACHE_KEY_PREFIX', prefix)

    yield

    with connection_pool.begin() as conn:
        conn.execute(text('DELETE FROM key_value_storage WHERE key LIKE :pattern'), {'pattern': f'{prefix}-%'})
