"""Function acts as API for the App designed to support LizaAlert Group of Phone Calls.
The current script retrieves an actual list active searches"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import functions_framework
from bs4 import BeautifulSoup
from flask import Request

from _dependencies.commons import get_app_config, setup_google_logging, sql_connect_by_psycopg2
from _dependencies.content import clean_up_content

setup_google_logging()


def get_list_of_allowed_apps():
    """get the list of app_ids approved by admin"""

    approved_app_ids = None

    try:
        data_string = get_app_config().api_clients
        approved_app_ids = eval(data_string)

    except Exception as e:
        logging.exception(e)
        logging.info('exception happened in getting list of allowed app_ids')

    return approved_app_ids


def get_list_of_active_searches_from_db(request: json) -> tuple:
    """retrieves a list of recent searches"""

    depth_days = 10000
    if 'depth_days' in request.keys() and isinstance(request['depth_days'], int):
        depth_days = request['depth_days']
    logging.info(f'{depth_days=}')

    folders_list = []
    if 'forum_folder_id_list' in request.keys() and isinstance(request['forum_folder_id_list'], list):
        folders_list = request['forum_folder_id_list']
    logging.info(f'{folders_list=}')

    searches_data = []
    conn_psy = sql_connect_by_psycopg2()
    cur = conn_psy.cursor()

    if folders_list:
        cur.execute(
            """WITH
            user_regions_filtered AS (
                SELECT DISTINCT folder_id AS forum_folder_num
                FROM geo_folders
                WHERE folder_type='searches' AND folder_id = ANY(%s)
            ),
            s2 AS (
                SELECT search_start_time, forum_folder_id, topic_type, search_forum_num,
                        status, display_name, family_name,
                age_min, age_max
                FROM searches
                WHERE forum_folder_id IN (SELECT forum_folder_num FROM user_regions_filtered)
                AND status NOT IN ('НЖ', 'НП', 'Завершен', 'Найден')
                AND topic_type_id != 1
                AND search_start_time >= CURRENT_TIMESTAMP - INTERVAL '%s days'
                ORDER BY search_start_time DESC
            ),
            s3 AS (SELECT s2.*
                FROM s2
                LEFT JOIN search_health_check shc
                ON s2.search_forum_num=shc.search_forum_num
                WHERE (shc.status is NULL OR shc.status='ok' OR shc.status='regular')
                ORDER BY s2.search_start_time DESC
            ),
            s4 AS (SELECT s3.*, sfp.content
                FROM s3
                LEFT JOIN search_first_posts AS sfp
                ON s3.search_forum_num=sfp.search_id
                WHERE sfp.actual = True
            )
            SELECT * FROM s4;""",
            (folders_list, depth_days),
        )
    else:
        cur.execute(
            """WITH
            user_regions_filtered AS (
                SELECT DISTINCT folder_id AS forum_folder_num
                FROM geo_folders
                WHERE folder_type='searches'
            ),
            s2 AS (
                SELECT search_start_time, forum_folder_id, topic_type, search_forum_num,
                        status, display_name, family_name,
                age_min, age_max
                FROM searches
                WHERE forum_folder_id IN (SELECT forum_folder_num FROM user_regions_filtered)
                AND status NOT IN ('НЖ', 'НП', 'Завершен', 'Найден')
                AND topic_type_id != 1
                AND search_start_time >= CURRENT_TIMESTAMP - INTERVAL '%s days'
                ORDER BY search_start_time DESC
            ),
            s3 AS (SELECT s2.*
                FROM s2
                LEFT JOIN search_health_check shc
                ON s2.search_forum_num=shc.search_forum_num
                WHERE (shc.status is NULL OR shc.status='ok' OR shc.status='regular')
                ORDER BY s2.search_start_time DESC
            ),
            s4 AS (SELECT s3.*, sfp.content
                FROM s3
                LEFT JOIN search_first_posts AS sfp
                ON s3.search_forum_num=sfp.search_id
                WHERE sfp.actual = True
            )
            SELECT * FROM s4;""",
            (depth_days,),
        )

    raw_data = cur.fetchall()

    if raw_data:
        for line in raw_data:
            (
                search_start_time,
                forum_folder_id,
                topic_type,
                search_id,
                status,
                display_name,
                family_name,
                age_min,
                age_max,
                first_post,
            ) = line

            # search_id, search_start_time, display_name, status, family_name, topic_type, topic_type_id, \
            # city_locations, age_min, age_max, first_post, lat, lon, coord_type, last_change_time = line

            logging.info(f'{search_id=}')

            # define "content"
            content = clean_up_content(first_post)

            user_search = {
                'search_start_time': search_start_time,
                'forum_folder_id': forum_folder_id,
                'search_type': topic_type,
                'search_id': search_id,
                'search_status': status,
                'display_name': display_name,
                'family_name': family_name,
                'age_min': age_min,
                'age_max': age_max,
                'content': content,
            }

            searches_data.append(user_search)

    cur.close()
    conn_psy.close()

    return searches_data


def save_user_statistics_to_db(user_input, response) -> None:
    """save user's interaction into DB"""

    json_to_save = json.dumps(response, default=str)

    conn_psy = sql_connect_by_psycopg2()
    cur = conn_psy.cursor()

    try:
        cur.execute(
            """INSERT INTO stat_api_usage_actual_searches
                       (request, timestamp, response)
                       VALUES (%s, CURRENT_TIMESTAMP, %s);""",
            (str(user_input), json_to_save),
        )

    except Exception as e:
        logging.exception(e)

    cur.close()
    conn_psy.close()

    return None


def verify_json_validity(user_input, list_of_allowed_apps):
    """verify the received message is eligible to be processed"""

    reason = None

    if not user_input or not isinstance(user_input, dict):  # or 'hash' not in user_input.keys():
        reason = 'No request or request is not a dict/json'

    elif 'app_id' not in user_input.keys():
        reason = 'No app_id provided'

    elif user_input['app_id'] not in list_of_allowed_apps:
        reason = 'Incorrect app_id'

    logging.info(f'the incoming json is {user_input=}, {reason=}')

    return reason


@functions_framework.http
def main(request: Request) -> Tuple[str, int, Dict[str, str]]:
    # For more information about CORS and CORS preflight requests, see:
    # https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request

    # Set CORS headers for the preflight request
    if request.method == 'OPTIONS':
        # Allows GET requests from any origin with the Content-Type
        # header and caches preflight response for 3600s
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': ['GET', 'OPTIONS'],
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600',
        }

        logging.info(f'{headers=}')

        return '', 204, headers

    # Set CORS headers for the main request
    headers = {'Access-Control-Allow-Origin': '*'}

    request_json = request.get_json(silent=True)
    logging.info(f'{request_json}')
    list_of_allowed_apps = get_list_of_allowed_apps()
    logging.info(f'{list_of_allowed_apps=}')
    reason_not_to_process_json = verify_json_validity(request_json, list_of_allowed_apps)

    if reason_not_to_process_json:
        response = {'ok': False, 'reason': reason_not_to_process_json}

        save_user_statistics_to_db(request_json, response)

        return json.dumps(response), 200, headers

    searches = get_list_of_active_searches_from_db(request_json)
    response = {'ok': True, 'searches': searches}

    save_user_statistics_to_db(request_json, response)

    logging.info(request)
    logging.info(request_json)
    logging.info(f'the RESULT {response}')

    return json.dumps(response, default=str), 200, headers
