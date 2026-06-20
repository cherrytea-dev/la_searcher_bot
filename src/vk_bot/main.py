import logging
import random
from typing import Any

from _dependencies.commons import setup_logging
from _dependencies.misc import (
    RequestWrapper,
    ResponseWrapper,
    request_response_converter,
)

from ._utils.event_dispatcher import dispatch_event

setup_logging(__package__)
random.seed()


@request_response_converter
def main(request: RequestWrapper, *args: Any, **kwargs: Any) -> ResponseWrapper:
    logging.info('Incoming http request %s', request)

    response = dispatch_event(request.json_)  # type:ignore[arg-type]
    return ResponseWrapper(data=response)
