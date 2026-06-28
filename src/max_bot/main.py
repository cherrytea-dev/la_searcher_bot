"""Yandex Cloud Function entry point for the MAX bot.

This function is triggered by an HTTP gateway (Yandex API Gateway)
that forwards MAX Callback API webhook events.

Currently supports only long-polling mode (see ``cli.py``).
Webhook mode will be added in a future iteration.

NOTE: The Yandex Cloud Function deployment uses ``max_bot.main.main``
as the entrypoint. For local development, use ``cli.py --polling``.
"""

import logging
import random

from _dependencies.common.commons import setup_logging
from _dependencies.common.misc import (
    RequestWrapper,
    ResponseWrapper,
    request_response_converter,
)

setup_logging(__package__)
random.seed()


@request_response_converter
def main(request: RequestWrapper, *args: object, **kwargs: object) -> ResponseWrapper:
    """Handle incoming HTTP request (webhook mode placeholder).

    Args:
        request: Incoming HTTP request wrapped in ``RequestWrapper``.

    Returns:
        HTTP response wrapped in ``ResponseWrapper``.

    TODO: Implement webhook handling using ``Dispatcher.handle_webhook()``
    when the MAX bot is deployed with a public HTTPS endpoint.
    """
    logging.info('Incoming http request %s', request)

    # Webhook mode not yet implemented — return 501
    return ResponseWrapper(data='Webhook mode not implemented yet', status_code=501)
