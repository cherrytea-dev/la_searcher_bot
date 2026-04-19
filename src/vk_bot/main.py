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

import sqlalchemy
from pydantic import BaseModel

from _dependencies.commons import TopicType, get_app_config, setup_logging, sqlalchemy_get_pool
from _dependencies.misc import (
    RequestWrapper,
    ResponseWrapper,
    request_response_converter,
    time_counter_since_search_start,
)

setup_logging(__package__)


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


class OptionsResponse(FlaskResponseBase):
    def as_response(self, origin_to_show: str) -> ResponseWrapper:
        # Allows GET requests from any origin with the Content-Type
        # header and caches preflight response for 3600s
        # For more information about CORS and CORS preflight requests, see:
        # https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request

        headers = {
            'Access-Control-Allow-Origin': origin_to_show,
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600',
        }

        logging.info(f'{headers=}')
        return ResponseWrapper('', 204, headers)


def get_origin_to_show(request: RequestWrapper) -> str:
    allowed_origins = [
        'https://web_app.storage.googleapis.com',
        'https://storage.googleapis.com',
        'https://storage.yandexcloud.net',
    ]
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

    if not isinstance(request_json, str) and 'id' not in request_json:
        logging.info(f'the incoming json is {request_json}')
        return FailResponse(reason='No user_id in json provided')

    if not isinstance(request_json, str) and 'id' in request_json and not isinstance(request_json['id'], int):
        return FailResponse(reason='user_id is not a digit')

    return None


@request_response_converter
def main(request: RequestWrapper, *args: Any, **kwargs: Any) -> ResponseWrapper:
    origin_to_show = get_origin_to_show(request)

    # Set CORS headers for the preflight request
    if request.method == 'OPTIONS':
        return OptionsResponse().as_response(origin_to_show)

    # Set CORS headers for the main request
    headers = {'Access-Control-Allow-Origin': origin_to_show}
    logging.info(f'{headers=}')

    logging.info(request)

    return ResponseWrapper('ok')
