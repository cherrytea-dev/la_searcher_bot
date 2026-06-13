"""Local Flask dev server for VK Admin Panel API.

Usage:
    uv run python -m src.vk_admin_api.cli

This starts a Flask server on http://localhost:8888 that wraps
the Yandex Cloud Function entrypoint for local development.
"""

from dotenv import load_dotenv

load_dotenv()  # must be before importing main, so os.getenv() sees .env vars

from flask import Flask
from flask import request as flask_request

from .main import main

app = Flask(__name__)


@app.route('/', defaults={'path': '/'}, methods=['GET', 'POST', 'OPTIONS', 'DELETE'])
@app.route('/<path:path>', methods=['GET', 'POST', 'OPTIONS', 'DELETE'])
def handler(path: str = '/'):
    """Pass the raw YC-format dict to main(); the @request_response_converter
    decorator on main() handles conversion to RequestWrapper."""
    yc_request = {
        'httpMethod': flask_request.method,
        'path': '/' + path,
        'headers': dict(flask_request.headers),
        'body': flask_request.get_data(as_text=True),
        'queryStringParameters': {},
    }
    result = main(yc_request)
    return result['body'], result['statusCode'], result.get('headers', {})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888)
