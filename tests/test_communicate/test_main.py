from unittest.mock import Mock

import pytest

from communicate import main


def test_main_mock():
    # just to run imports and calculate code coverage
    resp = main.main(Mock())
    assert resp.status_code == 200
    assert resp.data.decode() == 'it was not post request'
