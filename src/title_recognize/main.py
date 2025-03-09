import logging
from typing import Any

import functions_framework
from flask import Request
from pydantic import BaseModel, ConfigDict, ValidationError

from _dependencies.commons import setup_google_logging

from ._utils.recognizer import recognize_title

setup_google_logging()


class UserRequest(BaseModel):
    model_config = ConfigDict(extra='ignore')

    title: str
    reco_type: str | None = None


class FlaskResponseBase(BaseModel):
    status: str

    def as_response(self) -> str:
        return self.model_dump_json()


class FailResponse(FlaskResponseBase):
    fail_reason: str
    status: str = 'fail'


class OkResponse(FlaskResponseBase):
    title: str | None = None  # #do we need it?
    recognition: Any
    status: str = 'ok'


@functions_framework.http
def main(request: Request) -> str:
    """entry point to http-invoked cloud function"""

    try:
        user_request = UserRequest.model_validate_json(request.data)
        logging.info(f'Received request data: {user_request}')
    except ValidationError as ve:
        logging.info(f'Incorrect request data: {request.data.decode()}')
        return FailResponse(fail_reason=str(ve)).as_response()

    reco_title = recognize_title(user_request.title, user_request.reco_type)

    if not reco_title or ('topic_type' in reco_title.keys() and reco_title['topic_type'] == 'UNRECOGNIZED'):
        return FailResponse(fail_reason='not able to recognize', request=str(request.data)).as_response()

    logging.info(f'Response: {reco_title}')

    return OkResponse(title=user_request.title, recognition=reco_title).as_response()
