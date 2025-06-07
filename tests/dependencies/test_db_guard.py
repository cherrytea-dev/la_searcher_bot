from typing import NamedTuple
from uuid import uuid4

import pytest

from _dependencies.cloud_func_parallel_guard import (
    check_and_save_event_id,
    check_if_other_functions_are_working,
    record_finish_of_function,
    record_start_of_function,
)


class Context(NamedTuple):
    event_id: int


@pytest.fixture
def func_name() -> str:
    return uuid4().hex[:10]


def test_check_and_save_event_id(func_name: str):
    context = Context(event_id=123)
    res = check_and_save_event_id(
        context,
        'start',
        1,
        None,
        2,
        func_name,
        3,
    )
    assert not res


def test_check_and_save_event_id_blocked(func_name: str):
    context = Context(event_id=123)
    event_num = 123
    record_start_of_function(event_num, 2, 3, func_name)

    res = check_and_save_event_id(
        context,
        'start',
        1,
        None,
        2,
        func_name,
        3,
    )
    assert res


def test_record_is_blocked(func_name: str):
    interval = 5
    event_number = 7
    assert not check_if_other_functions_are_working(func_name, interval)
    record_start_of_function(event_number, 2, 3, func_name)
    assert check_if_other_functions_are_working(func_name, interval)
    record_finish_of_function(event_number, [])
    assert not check_if_other_functions_are_working(func_name, interval)
