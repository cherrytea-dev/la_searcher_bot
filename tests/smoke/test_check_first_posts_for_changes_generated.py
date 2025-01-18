import pytest

from check_first_posts_for_changes import main
from tests.common import run_smoke


def test_define_topic_visibility_by_content():
    res = run_smoke(main.define_topic_visibility_by_content)
    pass


def test_define_topic_visibility_by_topic_id():
    res = run_smoke(main.define_topic_visibility_by_topic_id)
    pass


def test_get_status_from_content_and_send_to_topic_management():
    res = run_smoke(main.get_status_from_content_and_send_to_topic_management)
    pass


def test_main():
    res = run_smoke(main.main)
    pass


def test_parse_search():
    res = run_smoke(main.parse_search)
    pass


def test_sql_connect():
    res = run_smoke(main.sql_connect)
    pass


def test_update_first_posts_and_statuses():
    res = run_smoke(main.update_first_posts_and_statuses)
    pass


def test_update_one_topic_visibility():
    res = run_smoke(main.update_one_topic_visibility)
    pass


def test_update_visibility_for_one_hidden_topic():
    res = run_smoke(main.update_visibility_for_one_hidden_topic)
    pass
