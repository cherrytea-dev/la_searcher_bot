import asyncio
import base64
import datetime
import logging
import random
from typing import Dict

import google.auth.transport.requests
import google.cloud.logging
import google.oauth2.id_token
import requests
from psycopg2.extensions import cursor
from telegram.ext import Application, ContextTypes

from _dependencies.commons import Topics, get_app_config, publish_to_pubsub


def notify_admin(message) -> None:
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub(Topics.topic_notify_admin, message)


def make_api_call(function: str, data: dict) -> dict:
    """makes an API call to another Google Cloud Function"""

    # function we're turing to "title_recognize"
    endpoint = f'https://europe-west3-lizaalert-bot-01.cloudfunctions.net/{function}'

    # required magic for Google Cloud Functions Gen2 to invoke each other
    audience = endpoint
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience)
    headers = {'Authorization': f'Bearer {id_token}', 'Content-Type': 'application/json'}

    r = requests.post(endpoint, json=data, headers=headers)
    content = r.json()

    return content


def process_pubsub_message(event: dict):
    """convert incoming pub/sub message into regular data"""

    # receiving message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
    else:
        received_message_from_pubsub = 'I cannot read message from pub/sub'
    encoded_to_ascii = eval(received_message_from_pubsub)
    data_in_ascii = encoded_to_ascii['data']
    message_in_ascii = data_in_ascii['message']

    return message_in_ascii


def process_pubsub_message_v2(event: dict):
    """get message from pub/sub notification"""

    # receiving message text from pub/sub
    try:
        if 'data' in event:
            received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
            encoded_to_ascii = eval(received_message_from_pubsub)
            data_in_ascii = encoded_to_ascii['data']
            message_in_ascii = data_in_ascii['message']
        else:
            message_in_ascii = 'ERROR: I cannot read message from pub/sub'
    except:  # noqa
        message_in_ascii = 'ERROR: I cannot read message from pub/sub'

    logging.info(f'received message from pub/sub: {message_in_ascii}')

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

    return [phrase, diff.days]


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


async def send_message_async(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=context.job.chat_id, **context.job.data)

    return None


async def prepare_message_for_async(user_id, data: Dict[str, str], bot_token: str) -> str:
    application = Application.builder().token(bot_token).build()
    job_queue = application.job_queue
    job_queue.run_once(send_message_async, 0, data=data, chat_id=user_id)

    async with application:
        await application.initialize()
        await application.start()
        await application.stop()
        await application.shutdown()

    return 'ok'


def process_sending_message_async_other_bot(user_id, data) -> None:
    # TODO same tokens or different?
    asyncio.run(prepare_message_for_async(user_id, data, bot_token=get_app_config().bot_api_token))


def process_sending_message_async(user_id: int, data) -> None:
    asyncio.run(prepare_message_for_async(user_id, data, bot_token=get_app_config().bot_api_token__prod))

    return None


def generate_random_function_id() -> int:
    """generates a random ID for every function – to track all function dependencies (no built-in ID in GCF)"""

    random_id = random.randint(100000000000, 999999999999)

    return random_id


def get_change_log_update_time(cur: cursor, change_log_id: int) -> datetime.datetime | None:
    """get he time of parsing of the change, saved in PSQL"""

    if not change_log_id:
        return None

    sql_text_psy = """
                    SELECT parsed_time 
                    FROM change_log 
                    WHERE id = %s;
                    /*action='getting_change_log_parsing_time' */;"""
    cur.execute(sql_text_psy, (change_log_id,))
    parsed_time = cur.fetchone()

    if not parsed_time:
        return None

    parsed_time = parsed_time[0]

    return parsed_time


def send_location_to_api(
    session: requests.Session, bot_token: str, user_id: str, params: dict
) -> requests.Response | None:
    """send location directly to Telegram API w/o any wrappers ar libraries"""

    try:
        latitude = ''
        longitude = ''
        if params:
            if 'latitude' in params.keys():
                latitude = f'&latitude={params["latitude"]}'
            if 'longitude' in params.keys():
                longitude = f'&longitude={params["longitude"]}'

        logging.info(latitude)
        logging.info(longitude)

        request_text = f'https://api.telegram.org/bot{bot_token}/sendLocation?chat_id={user_id}{latitude}{longitude}'

        r = session.get(request_text)

    except Exception as e:
        logging.exception(e)
        logging.info('Error in getting response from Telegram')
        r = None

    return r


def save_sending_status_to_notif_by_user(cur: cursor, message_id: int, result: str) -> None:
    """save the telegram sending status to sql table notif_by_user"""

    # TODO open and close cursor here
    if result[0:9] == 'cancelled':
        result = result[0:9]
    elif result[0:6] == 'failed':
        result = result[0:6]

    if result in {'completed', 'cancelled', 'failed'}:
        sql_text_psy = f"""
                    UPDATE notif_by_user
                    SET {result} = %s
                    WHERE message_id = %s;
                    /*action='save_sending_status_to_notif_by_user_{result}' */
                    ;"""

        cur.execute(sql_text_psy, (datetime.datetime.now(), message_id))


def evaluate_city_locations(city_locations):
    if not city_locations:
        logging.info('no city_locations')
        return None

    cl_eval = eval(city_locations)
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
