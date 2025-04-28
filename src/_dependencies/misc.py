import base64
import datetime
import json
import logging
import math
import random
import time
import urllib.parse
from ast import literal_eval
from functools import lru_cache
from typing import Any

import google.auth.transport.requests
import google.cloud.logging
import google.oauth2.id_token
import requests
from psycopg2.extensions import cursor
from retry import retry
from retry.api import retry_call

from _dependencies.commons import Topics, get_app_config, publish_to_pubsub
from _dependencies.telegram_api_wrapper import TGApiBase


@lru_cache
def tg_api_service_account() -> TGApiBase:
    return TGApiBase(token=get_app_config().bot_api_token)


@lru_cache
def tg_api_main_account() -> TGApiBase:
    return TGApiBase(token=get_app_config().bot_api_token__prod)


def notify_admin(message: str) -> None:
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub(Topics.topic_notify_admin, message)


@retry(Exception, tries=3, delay=3)
def make_api_call(function: str, data: dict) -> dict:
    """makes an API call to another Google Cloud Function"""

    # function we're turing to "title_recognize"
    endpoint = f'https://europe-west3-lizaalert-bot-01.cloudfunctions.net/{function}'

    # required magic for Google Cloud Functions Gen2 to invoke each other
    audience = endpoint
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience)
    headers = {'Authorization': f'Bearer {id_token}', 'Content-Type': 'application/json'}

    response = requests.post(endpoint, json=data, headers=headers, timeout=30)
    response.raise_for_status()
    content = response.json()

    return content


def process_pubsub_message(event: dict) -> str:
    """convert incoming pub/sub message into regular data"""

    # receiving message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
    else:
        received_message_from_pubsub = 'I cannot read message from pub/sub'
    encoded_to_ascii = literal_eval(received_message_from_pubsub)
    data_in_ascii = encoded_to_ascii['data']
    message_in_ascii = data_in_ascii['message']

    return message_in_ascii


def process_pubsub_message_v2(event: dict) -> str:
    """get message from pub/sub notification"""

    # receiving message text from pub/sub
    try:
        if 'data' in event:
            received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
            encoded_to_ascii = literal_eval(received_message_from_pubsub)
            data_in_ascii = encoded_to_ascii['data']
            message_in_ascii = data_in_ascii['message']
        else:
            message_in_ascii = 'ERROR: I cannot read message from pub/sub'
    except:  # noqa
        message_in_ascii = 'ERROR: I cannot read message from pub/sub'

    logging.info(f'received message from pub/sub: {message_in_ascii}')

    return message_in_ascii


def process_pubsub_message_v3(event: dict) -> str:
    """convert incoming pub/sub message into regular data"""
    # TODO DOUBLE

    # receiving message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
        logging.info('received_message_from_pubsub: ' + str(received_message_from_pubsub))
    elif 'message' in event:
        received_message_from_pubsub = base64.b64decode(event['message']).decode('utf-8')
    else:
        received_message_from_pubsub = 'I cannot read message from pub/sub'
        logging.info(received_message_from_pubsub)
    encoded_to_ascii = literal_eval(received_message_from_pubsub)
    logging.info('encoded_to_ascii: ' + str(encoded_to_ascii))
    try:
        data_in_ascii = encoded_to_ascii['data']
        logging.info('data_in_ascii: ' + str(data_in_ascii))
        message_in_ascii = data_in_ascii['message']
        logging.info('message_in_ascii: ' + str(message_in_ascii))
    except Exception as es:
        message_in_ascii = None
        logging.info('exception happened: ')
        logging.exception(str(es))

    return message_in_ascii


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


def get_change_log_update_time(cur: cursor, change_log_id: int) -> datetime.datetime | None:
    """get he time of parsing of the change, saved in PSQL"""
    # TODO optimize/cache

    if not change_log_id:
        return None

    sql_text_psy = """
                    SELECT parsed_time 
                    FROM change_log 
                    WHERE id = %s;
                    /*action='getting_change_log_parsing_time' */;"""
    cur.execute(sql_text_psy, (change_log_id,))
    record = cur.fetchone()

    if not record:
        return None

    return record[0]


def save_sending_status_to_notif_by_user(cur: cursor, message_id: int, result: str | None) -> None:
    """save the telegram sending status to sql table notif_by_user"""
    if not result:
        result = 'failed'

    if result.startswith('cancelled'):
        result = 'cancelled'
    elif result.startswith('failed'):
        result = 'failed'

    if result not in {'completed', 'cancelled', 'failed'}:
        return

    sql_text_psy = f"""
                UPDATE notif_by_user
                SET {result} = %s
                WHERE message_id = %s;
                /*action='save_sending_status_to_notif_by_user_{result}' */
                ;"""

    cur.execute(sql_text_psy, (datetime.datetime.now(), message_id))


def evaluate_city_locations(city_locations: str) -> list[list[Any]] | None:
    if not city_locations:
        logging.info('no city_locations')
        return None

    cl_eval = literal_eval(city_locations)
    if not cl_eval:
        logging.info('no eval of city_locations')
        return None

    if not isinstance(cl_eval, list):
        logging.info('eval of city_locations is not list')
        return None

    first_coords = cl_eval[0]

    if not first_coords:
        logging.info('no first coords in city_locations')
        return None

    if not isinstance(first_coords, list):
        logging.info('fist coords in city_locations is not list')
        return None

    logging.info(f'city_locations has coords {first_coords}')

    return [first_coords]


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
