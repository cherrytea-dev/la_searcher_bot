import logging
from unittest.mock import patch

from tests.common import get_dotenv_config, patched_send_topic, setup_logging_to_console
from vk_bot.cli import run_flask

if __name__ == '__main__':
    setup_logging_to_console()
    logging.info('hello')

    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        # patch('_dependencies.pubsub.send_topic_google', patched_send_topic),
    ):
        print('run following command to create temporal external address for your host')
        print('------------------')
        print('ssh -R 80:localhost:8888 nokey@localhost.run')
        print('------------------')
        run_flask('0.0.0.0', 8888)
