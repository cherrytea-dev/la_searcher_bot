import pytest

from check_topics_by_upd_time import main
from tests.common import run_smoke


def test_time_delta():
    res = run_smoke(main.time_delta)
    pass
