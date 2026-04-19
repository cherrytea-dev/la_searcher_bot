from _dependencies.misc import (
    RequestWrapper,
    ResponseWrapper,
    request_response_converter,
)

from .main import main_raw


def run_flask():
    from flask import Flask
    from flask import request as flask_request

    app = Flask(__name__)

    @app.post('/foo')
    def foo():
        req = RequestWrapper(method='post', data=flask_request.data, json_=flask_request.json, headers={})
        return main_raw(req).data

    app.run('0.0.0.0', '8888')


if __name__ == '__main__':
    run_flask()
