"""Function acts as API for the App designed to support LizaAlert Group of Phone Calls.
The current script retrieves an actual list active searches"""

import ast
import datetime
import json
import logging
from typing import Any

import sqlalchemy
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from _dependencies.common.commons import get_app_config, setup_logging
from _dependencies.common.db_client import DBClientBase
from _dependencies.common.misc import RequestWrapper, ResponseWrapper, request_response_converter
from _dependencies.forum.content import clean_up_content

setup_logging(__package__)


class Search(BaseModel):
    search_start_time: datetime.datetime
    forum_folder_id: int
    search_type: str
    search_id: int
    search_status: str
    display_name: str
    family_name: str
    age_min: int | None
    age_max: int | None
    content: str


class UserRequest(BaseModel):
    model_config = ConfigDict(extra='ignore')
    app_id: int | str
    forum_folder_id_list: list[int] = Field(default_factory=list)
    depth_days: int = 10000


class FlaskResponseBase(BaseModel):
    def as_response(self) -> ResponseWrapper:
        headers = {'Access-Control-Allow-Origin': '*'}
        return ResponseWrapper(self.model_dump_json(), 200, headers)


class FailResponse(FlaskResponseBase):
    reason: str
    ok: bool = False


class SuccessfulResponse(FlaskResponseBase):
    searches: list[Search]
    ok: bool = True


class OptionsResponse(FlaskResponseBase):
    def as_response(self) -> ResponseWrapper:
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

        return ResponseWrapper('', 204, headers)


class DBClient(DBClientBase):
    """DB client for api_get_active_searches."""

    def get_active_searches(self, request: UserRequest) -> list[Search]:
        """retrieves a list of recent searches"""
        searches = self._get_query_results(request.depth_days, request.forum_folder_id_list)
        for search in searches:
            search.content = str(clean_up_content(search.content))
        return searches

    def _get_query_results(self, depth_days: int, folders_list: list[int]) -> list[Search]:
        query = f"""
                WITH
                    user_regions_filtered AS (
                        SELECT DISTINCT folder_id AS forum_folder_num
                        FROM geo_folders
                        WHERE folder_type='searches' 
                        {'AND folder_id = ANY(:folders_list)' if folders_list else ''}
                    ),
                    s2 AS (
                        SELECT search_start_time, forum_folder_id, topic_type, search_forum_num,
                                status, display_name, family_name,
                        age_min, age_max
                        FROM searches
                        WHERE forum_folder_id IN (SELECT forum_folder_num FROM user_regions_filtered)
                        AND status NOT IN ('НЖ', 'НП', 'Завершен', 'Найден')
                        AND topic_type_id != 1
                        AND search_start_time >= CURRENT_TIMESTAMP - INTERVAL ':depth_days days'
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

        stmt = sqlalchemy.text(query)
        with self.connect() as conn:
            if folders_list:
                raw_data = conn.execute(stmt, dict(folders_list=folders_list, depth_days=depth_days)).fetchall()
            else:
                raw_data = conn.execute(stmt, dict(depth_days=depth_days)).fetchall()

        return [
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

    def save_user_statistics(self, user_input: Any, response: dict[str, Any]) -> None:
        """save user's interaction into DB"""
        json_to_save = json.dumps(response, default=str)
        try:
            with self.connect() as conn:
                stmt = sqlalchemy.text("""
                    INSERT INTO stat_api_usage_actual_searches
                    (request, timestamp, response)
                    VALUES (:request, CURRENT_TIMESTAMP, :response)
                """)
                conn.execute(stmt, dict(request=str(user_input), response=json_to_save))
        except Exception:
            logging.exception('Cannot save statistics to DB')


def get_list_of_allowed_apps() -> list[str]:
    """get the list of app_ids approved by admin"""

    approved_app_ids = []

    try:
        data_string = get_app_config().api_clients
        approved_app_ids = ast.literal_eval(data_string)

    except Exception:
        logging.exception('exception happened in getting list of allowed app_ids')
        # but we cannot check app_id later

    return approved_app_ids


@request_response_converter
def main(request_data: RequestWrapper, *args: Any, **kwargs: Any) -> ResponseWrapper:
    # Set CORS headers for the preflight request
    response: FlaskResponseBase

    if request_data.method == 'OPTIONS':
        return OptionsResponse().as_response()

    request_json = request_data.json_
    logging.info(request_json)

    db = DBClient()
    try:
        user_request = UserRequest.model_validate_json(request_data.data)
    except ValidationError as ve:
        response = FailResponse(reason=str(ve))
        db.save_user_statistics(request_json, response.model_dump())
        return response.as_response()

    if user_request.app_id not in get_list_of_allowed_apps():
        return FailResponse(reason='Incorrect app_id').as_response()

    searches = db.get_active_searches(user_request)
    response = SuccessfulResponse(searches=searches)

    db.save_user_statistics(request_json, response.model_dump())

    logging.info(request_data)
    logging.info(f'the RESULT {response}')

    return response.as_response()
