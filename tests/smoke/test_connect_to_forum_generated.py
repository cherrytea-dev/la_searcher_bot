import pytest

from connect_to_forum import main
from tests.common import run_smoke


def test_get_user_attributes():
    res = run_smoke(main.get_user_attributes)
    pass


def test_get_user_data():
    res = run_smoke(main.get_user_data)
    pass


def test_login_into_forum():
    res = run_smoke(main.login_into_forum)
    pass


def test_match_user_region_from_forum_to_bot():
    res = run_smoke(main.match_user_region_from_forum_to_bot)
    pass
