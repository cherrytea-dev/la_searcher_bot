import logging
import random
from typing import Any

from _dependencies.commons import get_app_config, setup_logging
from _dependencies.misc import (
    RequestWrapper,
    ResponseWrapper,
    request_response_converter,
)

from ._utils.dispatcher import dispatch_event

setup_logging(__package__)
random.seed()


def main_raw(request: dict) -> str:
    """Handle incoming VK Callback API request.

    Delegates to the new dispatcher for all event types.
    The dispatcher handles 'confirmation' handshake internally.
    """
    return dispatch_event(request)


@request_response_converter
def main(request: RequestWrapper, *args: Any, **kwargs: Any) -> ResponseWrapper:
    logging.info('Incoming http request %s', request)
    return ResponseWrapper(data=main_raw(request.json_))  # type:ignore[arg-type]
