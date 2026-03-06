import pytest

from communicate import main
from tests.common import get_http_request


def test_main_mock():
    # just to run imports and calculate code coverage
    request = get_http_request(method='OPTIONS')

    resp = main.main(request)

    assert resp['statusCode'] == 400
    assert resp['body'] == 'it was not post request'
