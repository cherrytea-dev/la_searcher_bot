from typing import NamedTuple
from uuid import uuid4

import pytest

from _dependencies.cloud_func_parallel_guard import (
    _check_if_other_functions_are_working,
    _record_finish_of_function,
    _record_start_of_function,
    check_and_save_event_id,
)


class Context(NamedTuple):
    event_id: int


@pytest.fixture
def func_name() -> str:
    return uuid4().hex[:10]


def test_check_and_save_event_id(func_name: str, connection_pool):
    context = Context(event_id=123)
    res = check_and_save_event_id(
        connection_pool,
        context,
        'start',
        1,
        None,
        2,
        func_name,
        3,
    )
    assert not res


def test_check_and_save_event_id_blocked(func_name: str, connection_pool):
    context = Context(event_id=123)
    event_num = 123
    _record_start_of_function(event_num, 2, 3, func_name, connection_pool)

    res = check_and_save_event_id(
        connection_pool,
        context,
        'start',
        1,
        None,
        2,
        func_name,
        3,
    )
    assert res


def test_record_is_blocked(func_name: str, connection_pool):
    interval = 5
    event_number = 7
    assert not _check_if_other_functions_are_working(func_name, interval, connection_pool)
    _record_start_of_function(event_number, 2, 3, func_name, connection_pool)
    assert _check_if_other_functions_are_working(func_name, interval, connection_pool)
    _record_finish_of_function(event_number, [], connection_pool)
    assert not _check_if_other_functions_are_working(func_name, interval, connection_pool)
