import datetime
import json
import logging
import math
import random
from dataclasses import dataclass, field
from functools import lru_cache, wraps
from typing import Any, Callable, Mapping, Sequence

import sqlalchemy
from flask import Request, Response

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


def calc_bearing(lat_2: float, lon_2: float, lat_1: float, lon_1: float) -> float:
    d_lon_ = lon_2 - lon_1
    x = math.cos(math.radians(lat_2)) * math.sin(math.radians(d_lon_))
    y = math.cos(math.radians(lat_1)) * math.sin(math.radians(lat_2)) - math.sin(math.radians(lat_1)) * math.cos(
        math.radians(lat_2)
    ) * math.cos(math.radians(d_lon_))
    bearing = math.atan2(x, y)  # used to determine the quadrant
    bearing = math.degrees(bearing)

    return bearing


@dataclass
class RequestWrapper:
    method: str
    data: bytes
    headers: dict[str, str] = field(default_factory=dict)
    json_: dict[str, Any] | None = None


@dataclass
class ResponseWrapper:
    data: str
    status_code: int = 200
    headers: Mapping[str, str | Sequence[str]] = field(default_factory=dict)


def request_response_converter(func: Callable[..., ResponseWrapper]) -> Callable[..., dict]:
    @wraps(func)
    def wrapper(request_data: dict, *args: Any, **kwargs: Any) -> dict:
        if isinstance(request_data, Request):
            # google branch
            request = convert_flask_request(request_data)
            response = func(request, *args, **kwargs)
            return Response(response.data, response.status_code, response.headers)
        else:
            # yc branch
            request = convert_yc_request(request_data)
            response = func(request, *args, **kwargs)
            return {'statusCode': response.status_code, 'body': response.data, 'headers': response.headers}

    return wrapper


def convert_yc_request(request_data: dict) -> RequestWrapper:
    """Convert Yandex Cloud Functions request format to RequestWrapper object"""

    try:
        json_ = json.loads(request_data.get('body'))  # type: ignore[arg-type]
    except:
        json_ = None

    return RequestWrapper(
        method=request_data.get('httpMethod'),  # type: ignore[arg-type]
        json_=json_,
        headers=request_data.get('headers', {}),
        data=request_data.get('body', b''),
    )


def convert_flask_request(request: Request) -> RequestWrapper:
    """Convert Yandex Cloud Functions request format to RequestWrapper object"""
    try:
        json_ = request.get_json()
    except:
        json_ = None

    return RequestWrapper(
        method=request.method,
        json_=json_,
        headers=request.headers,  # type: ignore[arg-type]
        data=request.data,
    )
