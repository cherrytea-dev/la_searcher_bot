import logging
import random
from contextlib import suppress
from typing import Any

from _dependencies.commons import get_app_config, setup_logging
from _dependencies.misc import (
    RequestWrapper,
    ResponseWrapper,
    request_response_converter,
)

from ._utils.bot_polling import UpdateEvent, process_incoming_message, run_polling

setup_logging(__package__)
random.seed()


def main_raw(request: dict) -> str:
    with suppress(Exception):
        if request['type'] == 'confirmation' and request['group_id'] == 237036024:
            # confirmation, run once
            return get_app_config().vk_confirmation_code

    event = UpdateEvent.model_validate(request)
    process_incoming_message(event)

    return 'ok'


@request_response_converter
def main(request: RequestWrapper, *args: Any, **kwargs: Any) -> ResponseWrapper:
    logging.info('Incoming http request %s', request)
    return ResponseWrapper(data=main_raw(request.json_))  # type:ignore[arg-type]


# if __name__ == '__main__':
#     run_polling()
#     # run_flask()
