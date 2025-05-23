from datetime import datetime, timedelta

import pytest

import _dependencies.pubsub
import send_notifications.main
from _dependencies import misc
from _dependencies.commons import sql_connect_by_psycopg2
from tests.common import get_event_with_data


def test_make_api_call():
    # TODO mock requests
    _dependencies.pubsub.recognize_title_via_api('test title', False)


@pytest.mark.parametrize(
    'minutes_ago,hours_ago,days_ago,result',
    [
        (0, 0, 0, ('Начинаем искать', 0)),
        (0, 1, 0, ('1 час', 0)),
        (0, 10, 0, ('10 часов', 0)),
        (0, 0, 2, ('2 дня', 2)),
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
            send_notifications.main.get_change_log_update_time(cursor, 1)


def test_save_sending_status_to_notif_by_user():
    with sql_connect_by_psycopg2() as connection:
        with connection.cursor() as cursor:
            send_notifications.main.save_sending_status_to_notif_by_user(cursor, 1, 'cancelled')


def test_process_pubsub_message():
    res = _dependencies.pubsub.process_pubsub_message(get_event_with_data('foo'))
    assert res == 'foo'


def test_process_pubsub_message_2():
    res = _dependencies.pubsub.process_pubsub_message(get_event_with_data('foo'))
    assert res == 'foo'


def test_process_pubsub_message_3():
    res = _dependencies.pubsub.process_pubsub_message(get_event_with_data('foo'))
    assert res == 'foo'
