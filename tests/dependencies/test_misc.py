from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import requests

from _dependencies import misc
from _dependencies.commons import sql_connect_by_psycopg2
from tests.common import get_test_config


def test_notify_admin(patch_pubsub_client, bot_mock_send_message: AsyncMock):
    data = 'some message'

    misc.notify_admin(data)
    bot_mock_send_message.assert_called_once_with(chat_id=get_test_config().my_telegram_id, text=data)


def test_make_api_call():
    # TODO mock requests
    misc.make_api_call('test', {'a: 1'})


@pytest.mark.parametrize(
    'minutes_ago,hours_ago,days_ago,result',
    [
        (0, 0, 0, ['Начинаем искать', 0]),
        (0, 1, 0, ['1 час', 0]),
        (0, 10, 0, ['10 часов', 0]),
        (0, 0, 2, ['2 дня', 2]),
    ],
)
def test_time_counter_since_search_start(minutes_ago: int, hours_ago: int, days_ago: int, result: str):
    start_datetime = datetime.now() - timedelta(minutes=minutes_ago, hours=hours_ago, days=days_ago)
    res = misc.time_counter_since_search_start(start_datetime)
    assert res == result


@pytest.mark.parametrize(
    'age,result',
    [
        (0, ''),
        (1, '1 год'),
        (5, '5 лет'),
        (22, '22 года'),
    ],
)
def test_age_writer(age: int, result: str):
    assert result == misc.age_writer(age)


def test_get_change_log_update_time():
    with sql_connect_by_psycopg2() as connection:
        with connection.cursor() as cursor:
            misc.get_change_log_update_time(cursor, 1)


def test_send_location_to_api():
    with requests.Session() as session:
        misc.send_location_to_api(
            session,
            get_test_config().bot_api_token,
            '2',
            {'latitude': 50, 'longitude': 50},
        )


def test_save_sending_status_to_notif_by_user():
    with sql_connect_by_psycopg2() as connection:
        with connection.cursor() as cursor:
            misc.save_sending_status_to_notif_by_user(cursor, 1, 'cancelled')


def test_evaluate_city_locations_success():
    res = misc.evaluate_city_locations('[[56.0, 64.0]]')
    assert res == [[56.0, 64.0]]


@pytest.mark.parametrize(
    'param',
    [
        [],
        [1],
        [None],
        '"foo"',
        '',
    ],
)
def test_evaluate_city_locations_fail(param):
    res = misc.evaluate_city_locations(str(param))
    assert res is None
