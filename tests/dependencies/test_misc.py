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


def test_convert_request():
    pass


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


def test_process_pubsub_message():
    res = _dependencies.pubsub.process_pubsub_message(get_event_with_data('foo'))
    assert res == 'foo'


def test_convert_flask_request():
    # example from https://yandex.cloud/ru/docs/functions/lang/python/handler
    inp = {
        'body': '{"hello": "world"}',
        'headers': {
            'Accept': '*/*',
            'Content-Length': '18',
            'Content-Type': 'application/json',
            'Host': 'functions.yandexcloud.net',
        },
        'httpMethod': 'POST',
        'isBase64Encoded': False,
        'multiValueHeaders': {
            'Accept': ['*/*'],
            'Content-Length': ['18'],
            'Content-Type': ['application/json'],
            'Host': ['functions.yandexcloud.net'],
        },
        'multiValueParams': {},
        'multiValueQueryStringParameters': {'param': ['one']},
        'params': {},
        'pathParams': {},
        'queryStringParameters': {'param': 'one'},
        'requestContext': {
            'httpMethod': 'POST',
            'identity': {'sourceIp': '109.252.148.209', 'userAgent': 'curl/7.64.1'},
            'requestId': '6e8356f9-489b-4c7b-8ba6-c8cd********',
            'requestTime': '13/Jul/2022:11:58:59 +0000',
            'requestTimeEpoch': 1657713539,
        },
        'url': '',
    }
    request_wrapper = misc.convert_yc_request(inp)
    assert request_wrapper.json_ == {'hello': 'world'}
    assert request_wrapper.method == 'POST'
    assert request_wrapper.headers['Content-Type'] == 'application/json'
