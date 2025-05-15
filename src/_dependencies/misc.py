import datetime
import json
import logging
import math
import random
from functools import lru_cache

import sqlalchemy

from _dependencies.commons import get_app_config
from _dependencies.telegram_api_wrapper import TGApiBase


@lru_cache
def tg_api_service_account() -> TGApiBase:
    return TGApiBase(token=get_app_config().bot_api_token)


@lru_cache
def tg_api_main_account() -> TGApiBase:
    return TGApiBase(token=get_app_config().bot_api_token__prod)


def time_counter_since_search_start(start_time: datetime.datetime) -> tuple[str, int]:
    """Count timedelta since the beginning of search till now, return phrase in Russian and diff in days"""

    start_diff = datetime.timedelta(hours=0)

    now = datetime.datetime.now()
    diff = now - start_time - start_diff

    first_word_parameter = ''

    # <20 minutes -> "Начинаем искать"
    if (diff.total_seconds() / 60) < 20:
        phrase = 'Начинаем искать'

    # 20 min - 1 hour -> "Ищем ХХ минут"
    elif (diff.total_seconds() / 3600) < 1:
        phrase = first_word_parameter + str(round(int(diff.total_seconds() / 60), -1)) + ' минут'

    # 1-24 hours -> "Ищем ХХ часов"
    elif diff.days < 1:
        phrase = first_word_parameter + str(int(diff.total_seconds() / 3600))
        if int(diff.total_seconds() / 3600) in {1, 21}:
            phrase += ' час'
        elif int(diff.total_seconds() / 3600) in {2, 3, 4, 22, 23}:
            phrase += ' часа'
        else:
            phrase += ' часов'

    # >24 hours -> "Ищем Х дней"
    else:
        phrase = first_word_parameter + str(diff.days)
        if str(int(diff.days))[-1] == '1' and (int(diff.days)) != 11:
            phrase += ' день'
        elif int(diff.days) in {12, 13, 14}:
            phrase += ' дней'
        elif str(int(diff.days))[-1] in {'2', '3', '4'}:
            phrase += ' дня'
        else:
            phrase += ' дней'

    return phrase, diff.days


def age_writer(age: int) -> str:
    """compose an age string with the right form of years in Russian"""

    if age:
        a = age // 100
        b = (age - a * 100) // 10
        c = age - a * 100 - b * 10
        if c == 1 and b != 1:
            wording = str(age) + ' год'
        elif (c == 2 or c == 3 or c == 4) and b != 1:
            wording = str(age) + ' года'
        else:
            wording = str(age) + ' лет'
    else:
        wording = ''

    return wording


def generate_random_function_id() -> int:
    """generates a random ID for every function – to track all function dependencies (no built-in ID in GCF)"""

    random_id = random.randint(100000000000, 999999999999)

    return random_id


def get_triggering_function(message_from_pubsub: dict) -> int:
    """get a function_id of the function, which triggered this function (if available)"""

    triggered_by_func_id = 0
    try:
        if (
            message_from_pubsub
            and isinstance(message_from_pubsub, dict)
            and 'triggered_by_func_id' in message_from_pubsub.keys()
        ):
            triggered_by_func_id = int(message_from_pubsub['triggered_by_func_id'])

    except Exception as e:
        logging.exception(e)

    if triggered_by_func_id:
        logging.info(f'this function is triggered by func-id {triggered_by_func_id}')
    else:
        logging.info('triggering func_id was not determined')

    return triggered_by_func_id


def calc_bearing(lat_2: float, lon_2: float, lat_1: float, lon_1: float) -> float:
    d_lon_ = lon_2 - lon_1
    x = math.cos(math.radians(lat_2)) * math.sin(math.radians(d_lon_))
    y = math.cos(math.radians(lat_1)) * math.sin(math.radians(lat_2)) - math.sin(math.radians(lat_1)) * math.cos(
        math.radians(lat_2)
    ) * math.cos(math.radians(d_lon_))
    bearing = math.atan2(x, y)  # used to determine the quadrant
    bearing = math.degrees(bearing)

    return bearing


def save_function_into_register(
    conn: sqlalchemy.engine.Connection,
    event_id: str,
    start_time: datetime.datetime,
    function_id: int,
    change_log_ids: list[int],
    function_name: str,
) -> None:
    """save current function into functions_registry"""
    # TODO merge with similar functions

    json_of_params = json.dumps({'ch_id': change_log_ids})

    sql_text = sqlalchemy.text("""
        INSERT INTO functions_registry
        (event_id, time_start, cloud_function_name, function_id,
        time_finish, params)
        VALUES (:a, :b, :c, :d, :e, :f)
                                """)
    conn.execute(
        sql_text,
        a=event_id,
        b=start_time,
        c=function_name,
        d=function_id,
        e=datetime.datetime.now(),
        f=json_of_params,
    )

    logging.info(f'function {function_id} was saved in functions_registry')
