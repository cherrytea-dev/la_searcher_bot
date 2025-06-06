import pytest
from flask import Flask

from communicate import main


@pytest.fixture
def app() -> Flask:
    return Flask(__name__)


def test_main_mock(app: Flask):
    # just to run imports and calculate code coverage
    with app.test_request_context('/', method='OPTIONS') as request_context:
        resp = main.main(request_context.request)
    assert resp.status_code == 400
    assert resp.data.decode() == 'it was not post request'
