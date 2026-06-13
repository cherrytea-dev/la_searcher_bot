"""Local Flask dev server for VK Admin Panel API.

Usage:
    uv run python -m src.vk_admin_api.cli

This starts a Flask server on http://localhost:8888 that wraps
the Yandex Cloud Function entrypoint for local development.
"""

from flask import Flask, request as flask_request
from _dependencies.misc import convert_yc_request
from .main import main

app = Flask(__name__)


@app.route('/', methods=['GET', 'POST', 'OPTIONS', 'DELETE'])
def handler():
    yc_request = convert_yc_request(
        {
            'httpMethod': flask_request.method,
            'headers': dict(flask_request.headers),
            'body': flask_request.get_data(as_text=True),
            'queryStringParameters': {},
        }
    )
    result = main(yc_request)
    return result.body, result.status_code, dict(result.headers)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888)
