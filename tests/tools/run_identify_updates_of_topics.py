from unittest.mock import Mock, patch

from _dependencies import pubsub
from identify_updates_of_topics import main
from identify_updates_of_topics._utils import folder_updater
from tests.common import get_dotenv_config, get_event_with_data, setup_logging
from title_recognize.main import recognize_title


def fake_publish_to_pubsub(topic, message):
    print(f'Publishing to Pub/Sub topic: {topic}, message: {message}')


def fake_recognize_title_via_api(title: str, status_only: bool):
    reco_data = recognize_title(title, False)
    return {'status': 'ok', 'recognition': reco_data}


if __name__ == '__main__':
    setup_logging()
    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        patch.object(pubsub, 'publish_to_pubsub', fake_publish_to_pubsub),
        patch.object(folder_updater, 'recognize_title_via_api', fake_recognize_title_via_api),
    ):
        folders = [(276, None)]
        data = get_event_with_data(str(folders))
        context = Mock()
        context.event_id = 123

        main.main(data, context)
