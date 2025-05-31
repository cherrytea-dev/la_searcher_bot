"""Function acts as API for Searches Map WebApp made as a part of Searcher Bot
The current script checks Telegram authentication and retrieves user's key data and list of searches"""

import ast
import hashlib
import hmac
import json
import logging
import re
from ast import literal_eval
from typing import Any
from urllib.parse import unquote

from psycopg2.extensions import connection
from pydantic import BaseModel

from _dependencies.commons import TopicType, get_app_config, setup_google_logging, sql_connect_by_psycopg2
from _dependencies.content import clean_up_content
from _dependencies.misc import (
    RequestWrapper,
    ResponseWrapper,
    request_response_converter,
    time_counter_since_search_start,
)

setup_google_logging()


class FlaskResponseBase(BaseModel):
    def as_response(self, origin_to_show: str) -> ResponseWrapper:
        headers = {
            'Access-Control-Allow-Origin': origin_to_show,
            'content-type': 'application/json',
        }
        return ResponseWrapper(self.model_dump_json(), 200, headers)


class FailResponse(FlaskResponseBase):
    reason: str
    ok: bool = False


class Search(BaseModel):
    name: int
    coords: list[list[float]]
    exact_coords: bool
    content: str
    display_name: str
    freshness: str
    link: str
    search_status: str
    search_type: str
    search_is_old: bool


class BaseUserParams(BaseModel):
    curr_user: bool
    home_lat: float | None
    home_lon: float | None
    radius: int | None
    regions: list[int]
    searches: list[Search]


class DemoUserParams(BaseUserParams):
    """some default params for demo user"""

    curr_user: bool = False
    home_lat: float = 55.752702  # Kremlin
    home_lon: float = 37.622914  # Kremlin
    radius: int = 100  # demo radius = 100 km
    regions: list[int] = [28, 29]  # Moscow + Moscow Region


class FoundUserParams(BaseUserParams):
    user_id: int  # TODO can we return user_id for demo user?


class OkResponse(FlaskResponseBase):
    user_id: int
    params: BaseUserParams
    ok: bool = True


class OptionsResponse(FlaskResponseBase):
    def as_response(self, origin_to_show: str) -> ResponseWrapper:
        # Allows GET requests from any origin with the Content-Type
        # header and caches preflight response for 3600s
        # For more information about CORS and CORS preflight requests, see:
        # https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request

        headers = {
            'Access-Control-Allow-Origin': origin_to_show,
            'Access-Control-Allow-Methods': ['GET', 'OPTIONS'],
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600',
        }

        logging.info(f'{headers=}')
        return ResponseWrapper('', 204, headers)


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


def get_user_data_from_db(user_id: int) -> BaseUserParams:
    """if user_is is a current bot's user – than retrieves user's data like home coords, radius, list of searches
    if user_id is not a user of bot – than retrieves a "demo" data with fake home coords, radius and real list of
    searches for Moscow Region"""

    with sql_connect_by_psycopg2() as conn_psy:
        user_params = _compose_basic_user_params(user_id, conn_psy)
        if not user_params:
            return DemoUserParams(
                searches=_get_searches_from_db(user_id, conn_psy, False),
            )

        user_params['regions'] = _get_user_regions(user_id, conn_psy)
        user_params['searches'] = _get_searches_from_db(user_id, conn_psy, True)

    return FoundUserParams(**user_params)


def _get_searches_from_db(user_id: int, conn_psy: connection, user_was_found: bool) -> list[Search]:
    filter_condition = 'WHERE user_id=%s' if user_was_found else 'WHERE forum_folder_num=276 OR forum_folder_num=41'
    # create searches list – FOR DEMO ONLY Moscow Region (folders 276 and 41)

    query = f"""
    WITH
        user_regions AS (
            SELECT forum_folder_num from user_regional_preferences
            {filter_condition}),
        user_regions_filtered AS (
            SELECT ur.*
            FROM user_regions AS ur
            LEFT JOIN geo_folders AS f
            ON ur.forum_folder_num=f.folder_id
            WHERE f.folder_type='searches'),
        s2 AS (SELECT search_forum_num, search_start_time, display_name, status, family_name,
            topic_type, topic_type_id, city_locations, age_min, age_max
            FROM searches
            WHERE forum_folder_id IN (SELECT forum_folder_num FROM user_regions_filtered)
            AND status != 'НЖ'
            AND status != 'НП'
            AND status != 'Завершен'
            AND status != 'Найден'
            AND topic_type_id != 1
            ORDER BY search_start_time DESC
            LIMIT 30),
        s3 AS (SELECT s2.*
            FROM s2
            LEFT JOIN search_health_check shc
            ON s2.search_forum_num=shc.search_forum_num
            WHERE (shc.status is NULL OR shc.status='ok' OR shc.status='regular')
            ORDER BY s2.search_start_time DESC),
        s4 AS (SELECT s3.*, sfp.content
            FROM s3
            LEFT JOIN search_first_posts AS sfp
            ON s3.search_forum_num=sfp.search_id
            WHERE sfp.actual = True),
        s5 AS (SELECT s4.*, sc.latitude, sc.longitude, sc.coord_type
            FROM s4
            LEFT JOIN search_coordinates AS sc
            ON s4.search_forum_num=sc.search_id)
        SELECT distinct s5.*, max(parsed_time) OVER (PARTITION BY cl.search_forum_num) AS last_change_time
            FROM s5
            LEFT JOIN change_log AS cl
            ON s5.search_forum_num=cl.search_forum_num;
            """
    with conn_psy.cursor() as cur:
        cur.execute(query, (user_id,))
        raw_data = cur.fetchall()

    return _compose_searches(raw_data)


def _get_user_regions(user_id: int, conn_psy: connection) -> list[int]:
    # create folders (regions) list
    with conn_psy.cursor() as cur:
        cur.execute(
            """
            WITH
                step_0 AS (
                    SELECT
                        urp.forum_folder_num,
                        f.division_id AS region_id,
                        r.polygon_id
                    FROM user_regional_preferences AS urp
                    LEFT JOIN geo_folders AS f
                    ON urp.forum_folder_num=f.folder_id
                    JOIN geo_regions AS r
                    ON f.division_id=r.division_id
                    WHERE urp.user_id=%s
                )
            SELECT distinct polygon_id
            FROM step_0
            ORDER BY 1;
            """,
            (user_id,),
        )

        raw_data = cur.fetchall()
    if not raw_data:
        return []
    return [line[0] for line in raw_data]


def _compose_basic_user_params(user_id: int, conn_psy: connection) -> dict[str, Any] | None:
    # create user basic parameters
    with conn_psy.cursor() as cur:
        cur.execute(
            """
            SELECT u.user_id, uc.latitude, uc.longitude, ur.radius
            FROM users AS u
            LEFT JOIN user_coordinates AS uc
            ON u.user_id=uc.user_id
            LEFT JOIN user_pref_radius AS ur
            ON uc.user_id=ur.user_id
            WHERE u.user_id=%s;
            """,
            (user_id,),
        )
        raw_data = cur.fetchone()

    if not raw_data:
        return None

    else:
        user_params = {
            'curr_user': True,
            'user_id': raw_data[0],
            'home_lat': float(raw_data[1]) if raw_data[1] else None,
            'home_lon': float(raw_data[2]) if raw_data[2] else None,
            'radius': raw_data[3],
        }
    return user_params


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


def _compose_searches(raw_data: list[tuple]) -> list[Search]:  # TODO contract
    if not raw_data:
        return []

    user_searches = []
    for line in raw_data:
        (
            search_id,
            search_start_time,
            display_name,
            status,
            family_name,
            topic_type,
            topic_type_id,
            city_locations,
            age_min,
            age_max,
            first_post,
            lat,
            lon,
            coord_type,
            last_change_time,
        ) = line

        # define "freshness" of the search
        creation_freshness, creation_freshness_days = time_counter_since_search_start(search_start_time)
        update_freshness, update_freshness_days = time_counter_since_search_start(last_change_time)
        logging.info(f'{search_id=}')
        logging.info(f'{creation_freshness_days=}')
        logging.info(f'{update_freshness_days=}')
        logging.info(f'{min(creation_freshness_days, update_freshness_days)=}')
        search_is_old = creation_freshness_days > 3 and update_freshness_days > 3

        # define "exact_coords" – an variable showing if coordinates are explicityply provided ("exact")
        # or geocoded (not "exact")
        if not coord_type:
            exact_coords = False
        else:
            exact_coords = coord_type in {'1. coordinates w/ word coord', '2. coordinates w/o word coord'}

        # define "coords"
        if exact_coords:
            coords = [[ast.literal_eval(lat), ast.literal_eval(lon)]]
        else:
            coords = evaluate_city_locations(city_locations)  # type:ignore[assignment]

            if not coords and lat and lon:
                coords = [[ast.literal_eval(lat), ast.literal_eval(lon)]]
            elif not coords:
                coords = [[]]

        search_type = 'Обычный поиск' if topic_type_id == TopicType.search_regular else 'Особый поиск'
        # TODO – to be decomposed in greater details

        user_search = Search(
            name=search_id,
            coords=coords,
            exact_coords=exact_coords,
            content=str(clean_up_content(first_post)),
            display_name=display_name,
            freshness=creation_freshness,
            link=f'https://lizaalert.org/forum/viewtopic.php?t={search_id}',
            search_status=status,
            search_type=search_type,
            search_is_old=search_is_old,
        )

        if coords[0]:
            # not showing searches without coordsinates on map
            user_searches.append(user_search)

    return user_searches


def save_user_statistics_to_db(user_id: int, response: bool) -> None:
    """save user's interaction into DB"""

    json_to_save = json.dumps({'ok': response})

    conn_psy = sql_connect_by_psycopg2()
    cur = conn_psy.cursor()

    try:
        cur.execute(
            """
            INSERT INTO stat_map_usage
            (user_id, timestamp, response)
            VALUES (%s, CURRENT_TIMESTAMP, %s);
            """,
            (user_id, json_to_save),
        )
    except Exception as e:
        logging.exception(e)

    cur.close()
    conn_psy.close()

    return None


def get_origin_to_show(request: RequestWrapper) -> str:
    allowed_origins = ['https://web_app.storage.googleapis.com', 'https://storage.googleapis.com']
    origin = None
    try:
        origin = request.headers.get('Origin')
        logging.info(f'{origin=}')

    except Exception:
        logging.exception('No header Origin found')

    origin_to_show = origin if origin in allowed_origins else allowed_origins[1]
    logging.info(f'{origin_to_show=}')
    return origin_to_show


def validate_request(request: RequestWrapper) -> FailResponse | None:
    request_json = request.json_
    if not request_json:
        # logging.info(request.args)
        return FailResponse(reason='No json/string received')

    if not verify_telegram_data(request_json):
        logging.info(f'the incoming json is {request_json}')
        return FailResponse(reason='Provided json is not validated')

    if not isinstance(request_json, str) and 'id' not in request_json:
        logging.info(f'the incoming json is {request_json}')
        return FailResponse(reason='No user_id in json provided')

    if not isinstance(request_json, str) and 'id' in request_json and not isinstance(request_json['id'], int):
        return FailResponse(reason='user_id is not a digit')

    return None


def get_user_id(request_data: str | dict) -> int:
    if not isinstance(request_data, str):
        user_id = request_data['id']
    else:
        user_item = unquote(request_data)
        user_id = int(re.findall(r'(?<="id":)\d{3,20}', user_item)[0])
    logging.info(f'YES, {user_id=} is received!')
    return user_id


@request_response_converter
def main(request: RequestWrapper) -> ResponseWrapper:
    origin_to_show = get_origin_to_show(request)

    # Set CORS headers for the preflight request
    if request.method == 'OPTIONS':
        return OptionsResponse().as_response(origin_to_show)

    # Set CORS headers for the main request
    headers = {'Access-Control-Allow-Origin': origin_to_show}
    logging.info(f'{headers=}')

    logging.info(request)

    logging.info(f'the incoming json is {request.json_}')

    fail_response = validate_request(request)
    if fail_response:
        # MEMO - below we use "0" only to track number of unsuccessful api calls
        logging.info(f'reason={fail_response.reason}')
        save_user_statistics_to_db(0, False)
        return fail_response.as_response(origin_to_show)

    user_id = get_user_id(request.json_)  # type:ignore[arg-type]
    params = get_user_data_from_db(user_id)
    save_user_statistics_to_db(user_id, True)

    response = OkResponse(
        user_id=user_id,
        params=params,
    )
    logging.info(f'the RESULT {response}')
    return response.as_response(origin_to_show)
