import pytest

from .db_factories import NotifByUserFactory


@pytest.mark.skip(reason='helper for factories tuning')
def test_create_model():
    model = NotifByUserFactory.create_sync()
    assert model
