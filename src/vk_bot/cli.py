from _dependencies.misc import (
    RequestWrapper,
    ResponseWrapper,
    request_response_converter,
)

from ._utils.bot_polling import run_polling
from .main import main_raw


def run_flask() -> None:
    from flask import Flask, request  # type:ignore[import-not-found]

    app = Flask(__name__)

    @app.post('/foo')
    def foo() -> str:
        return main_raw(request.data)

    app.run('0.0.0.0', '8888')


if __name__ == '__main__':
    run_polling()
    # run_flask()
