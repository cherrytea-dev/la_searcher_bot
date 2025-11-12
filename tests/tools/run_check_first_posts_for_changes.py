from unittest.mock import patch

from check_first_posts_for_changes import main
from tests.common import get_dotenv_config, patched_send_topic, setup_logging_to_console

if __name__ == '__main__':
    setup_logging_to_console()
    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        patch('_dependencies.yandex_tools._send_topic', patched_send_topic),
    ):
        main.main('', '')
