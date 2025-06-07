from unittest.mock import patch

from _dependencies import pubsub
from check_topics_by_upd_time import main
from tests.common import get_dotenv_config, setup_logging_to_console


def fake_publish_to_pubsub(topic, message):
    print(f'Publishing to Pub/Sub topic: {topic}, message: {message}')


if __name__ == '__main__':
    setup_logging_to_console()
    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        patch.object(pubsub, 'publish_to_pubsub', fake_publish_to_pubsub),
    ):
        # main.main(get_event_with_data(str(generate_random_param())), '')
        main.main('', '')
