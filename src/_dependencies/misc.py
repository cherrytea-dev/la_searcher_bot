import datetime
import hashlib
import hmac
import json
import math
import random
from dataclasses import dataclass, field
from functools import lru_cache, wraps
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import unquote

from _dependencies.commons import get_app_config
from _dependencies.telegram_api_wrapper import TGApiBase


@lru_cache
def tg_api_service_account() -> TGApiBase:
    config = get_app_config()
    return TGApiBase(token=config.bot_api_token, host=config.bot_api_host)


@lru_cache
def tg_api_main_account() -> TGApiBase:
    config = get_app_config()
    return TGApiBase(token=config.bot_api_token__prod, host=config.bot_api_host)


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


# ─── Telegram Login Widget Verification ─────────────────────────────────


def verify_telegram_data_json(user_input: dict, token: str) -> bool:
    """verify the received dict is issued by telegram, which means user is authenticated with telegram"""

    if not user_input or not isinstance(user_input, dict) or 'hash' not in user_input.keys() or not token:
        return False

    hash_from_telegram = user_input['hash']
    sorted_dict = {key: value for key, value in sorted(user_input.items())}

    data_array = []
    for key, value in sorted_dict.items():
        if key != 'hash':
            data_array.append(f'{key}={value}')
    data_check_string = '\n'.join(data_array)

    # Convert bot_token to bytes and compute its SHA256 hash
    secret_key = hashlib.sha256(token.encode()).digest()

    # Compute the HMAC-SHA-256 signature of the data_check_string
    hmac_signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    # Compare the computed signature with the received hash
    return hmac_signature == hash_from_telegram


def verify_telegram_data_string(user_input: str, token: str) -> bool:
    """verify the received dict is issued by telegram, which means user is authenticated with telegram"""

    data_check_string = unquote(user_input)

    data_check_arr = data_check_string.split('&')
    needle = 'hash='
    hash_item = ''
    telegram_hash = ''
    for item in data_check_arr:
        if item[0 : len(needle)] == needle:
            telegram_hash = item[len(needle) :]
            hash_item = item
    data_check_arr.remove(hash_item)
    data_check_arr.sort()
    data_check_string = '\n'.join(data_check_arr)
    secret_key = hmac.new('WebAppData'.encode(), token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    return calculated_hash == telegram_hash


def verify_telegram_data(user_input: str | dict) -> bool:
    """verify the authority of user input with hash"""
    bot_token = get_app_config().bot_api_token__prod
    if isinstance(user_input, str):
        return verify_telegram_data_string(user_input, bot_token)
    else:
        return verify_telegram_data_json(user_input, bot_token)
