"""Function acts as API for the App designed to support LizaAlert Group of Phone Calls.
The current script retrieves an actual list active searches"""

import ast
import datetime
import json
import logging
from typing import Any

import functions_framework
from flask import Request
from psycopg2.extensions import connection
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from _dependencies.commons import get_app_config, setup_google_logging, sql_connect_by_psycopg2
from _dependencies.content import clean_up_content

setup_google_logging()


class Search(BaseModel):
    search_start_time: datetime.datetime
    forum_folder_id: int
    search_type: str
    search_id: int
    search_status: str
    display_name: str
    family_name: str
    age_min: int
    age_max: int
    content: str


class UserRequest(BaseModel):
    model_config = ConfigDict(extra='ignore')
    app_id: int | str
    forum_folder_id_list: list[int] = Field(default_factory=list)
    depth_days: int = 10000


class FlaskResponseBase(BaseModel):
    def as_response(self) -> tuple[str, int, dict]:
        headers = {'Access-Control-Allow-Origin': '*'}
        return self.model_dump_json(), 200, headers


class FailResponse(FlaskResponseBase):
    reason: str
    ok: bool = False


class SuccessfulResponse(FlaskResponseBase):
    searches: list[Search]
    ok: bool = True


class OptionsResponse(FlaskResponseBase):
    def as_response(self) -> tuple[str, int, dict]:
        # Allows GET requests from any origin with the Content-Type
        # header and caches preflight response for 3600s
        # For more information about CORS and CORS preflight requests, see:
        # https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request

        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': ['GET', 'OPTIONS'],
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600',
        }

        logging.info(f'{headers=}')

        return '', 204, headers


def get_list_of_allowed_apps() -> list[str]:
    """get the list of app_ids approved by admin"""

    approved_app_ids = []

    try:
        data_string = get_app_config().api_clients
        approved_app_ids = ast.literal_eval(data_string)

    except Exception as e:
        logging.exception('exception happened in getting list of allowed app_ids')
        # but we cannot check app_id later

    return approved_app_ids


def get_list_of_active_searches_from_db(conn_psy: connection, request: UserRequest) -> list[Search]:
    """retrieves a list of recent searches"""

    searches = get_query_results(conn_psy, request.depth_days, request.forum_folder_id_list)

    for line in searches:
        line.content = str(clean_up_content(line.content))

    return searches


def get_query_results(conn_psy: connection, depth_days: int, folders_list: list[int]) -> list[Search]:
    with conn_psy.cursor() as cur:
        query = f"""
            WITH
                user_regions_filtered AS (
                    SELECT DISTINCT folder_id AS forum_folder_num
                    FROM geo_folders
                    WHERE folder_type='searches' 
                    {'AND folder_id = ANY(%s)' if folders_list else ''}
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
                SELECT * FROM s4;
                """

        args = (folders_list, depth_days) if folders_list else (depth_days,)
        cur.execute(query, args)

        raw_data = cur.fetchall()

    searches = [
        Search(
            search_start_time=line[0],
            forum_folder_id=line[1],
            search_type=line[2],
            search_id=line[3],
            search_status=line[4],
            display_name=line[5],
            family_name=line[6],
            age_min=line[7],
            age_max=line[8],
            content=line[9],
        )
        for line in raw_data
    ]
    return searches


def save_user_statistics_to_db(conn_psy: connection, user_input: Any, response: dict[str, Any]) -> None:
    """save user's interaction into DB"""

    # TODO accept connection in args
    json_to_save = json.dumps(response, default=str)

    with conn_psy.cursor() as cur:
        try:
            cur.execute(
                """INSERT INTO stat_api_usage_actual_searches
                        (request, timestamp, response)
                        VALUES (%s, CURRENT_TIMESTAMP, %s);""",
                (str(user_input), json_to_save),
            )

        except Exception as e:
            logging.exception('Cannot save statistics to DB')


@functions_framework.http
def main(request: Request) -> tuple[str, int, dict[str, str]]:
    # Set CORS headers for the preflight request
    response: FlaskResponseBase

    if request.method == 'OPTIONS':
        return OptionsResponse().as_response()

    request_json = request.get_json(silent=True)
    logging.info(request_json)

    with sql_connect_by_psycopg2() as conn_psy:
        try:
            user_request = UserRequest.model_validate_json(request.data)
        except ValidationError as ve:
            response = FailResponse(reason=str(ve))
            save_user_statistics_to_db(conn_psy, request_json, response.model_dump())
            return response.as_response()

        if user_request.app_id not in get_list_of_allowed_apps():
            return FailResponse(reason='Incorrect app_id').as_response()

        searches = get_list_of_active_searches_from_db(conn_psy, user_request)
        response = SuccessfulResponse(searches=searches)

        save_user_statistics_to_db(conn_psy, request_json, response.model_dump())

    logging.info(request)
    logging.info(f'the RESULT {response}')

    return response.as_response()
