import pytest

from archive_notifications import main
from tests.common import run_smoke


def test_main():
    res = run_smoke(main.main)
    pass


def test_move_first_posts_to_history_in_psql():
    res = run_smoke(main.move_first_posts_to_history_in_psql)
    pass


def test_move_notifications_to_history_in_psql():
    res = run_smoke(main.move_notifications_to_history_in_psql)
    pass


def test_sql_connect():
    res = run_smoke(main.sql_connect)
    pass
