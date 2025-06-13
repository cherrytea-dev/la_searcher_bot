from unittest.mock import patch

from compose_notifications import main
from tests.common import get_dotenv_config, get_event_with_data, patched_send_topic, setup_logging_to_console

if __name__ == '__main__':
    setup_logging_to_console()
    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        patch('_dependencies.yandex_tools._send_topic', patched_send_topic),
    ):
        event = get_event_with_data('foo')
        main.main(event, '')
