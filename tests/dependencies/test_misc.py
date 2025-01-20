from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

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


# TODO remove after refactored

# NO SMOKE TEST api_get_active_searches.main.clean_up_content
# NO SMOKE TEST api_get_active_searches.main.evaluate_city_locations
# NO SMOKE TEST api_get_active_searches.main.time_counter_since_search_start
# NO SMOKE TEST check_topics_by_upd_time.main.notify_admin
# NO SMOKE TEST api_get_active_searches.time_counter_since_search_start.clean_up_content
# NO SMOKE TEST communicate.main.time_counter_since_search_start
# NO SMOKE TEST connect_to_forum.main.get_user_id
# NO SMOKE TEST identify_updates_of_topics.main.process_pubsub_message
# NO SMOKE TEST identify_updates_of_first_posts.main.process_pubsub_message
# NO SMOKE TEST identify_updates_of_first_posts.main.clean_up_content
# NO SMOKE TEST user_provide_info.main.clean_up_content
# NO SMOKE TEST user_provide_info.main.evaluate_city_locations
# NO SMOKE TEST user_provide_info.main.time_counter_since_search_start
