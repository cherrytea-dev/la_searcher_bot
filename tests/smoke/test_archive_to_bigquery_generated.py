import pytest

from archive_to_bigquery import main
from tests.common import run_smoke


def test_archive_notif_by_user():
    res = run_smoke(main.archive_notif_by_user)
    pass


def test_main():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.main)
    pass


def test_save_sql_stat_table_sizes():
    res = run_smoke(main.save_sql_stat_table_sizes)
    pass


def test_sql_connect():
    res = run_smoke(main.sql_connect)
    pass
