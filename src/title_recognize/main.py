import json
from typing import Union, Dict

import functions_framework


def get_requested_title(request: Union[Dict, None]) -> str:
    """gets the title from the incoming request"""

    request_json = request.get_json(silent=True)  # for the case when request contains json
    request_args = request.args  # for the case when request URLquery parameters

    if request_json and 'title' in request_json:
        title = request_json['title']

    elif request_args and 'title' in request_args:
        title = request_args['title']
    else:
        title = None

    return title


def title_recognition(title: str) -> Union[Dict, None]:
    """recognize the title and compose a dict with recognized values"""

    if not title:
        return None

    mock_reco = {"key_1": "value_1", "key_2": "value_2"}
    return mock_reco


@functions_framework.http
def main(request):
    """HTTP Cloud Function"""

    title = get_requested_title(request)

    if not title:
        response = {'get_title': 'fail', 'request': str(request.data)}
        response_json = json.dumps(response)
        return response_json

    reco_title = title_recognition(title)

    if not reco_title:
        response = {'get_title': 'ok', 'reco_status': 'fail', 'title': title, 'request': str(request.data)}
        response_json = json.dumps(response)
        return response_json

    response = {'get_title': 'ok', 'reco_status': 'ok', 'title': title, 'recognition': reco_title,
                'request': str(request.data)}
    response_json = json.dumps(response)

    return response_json
