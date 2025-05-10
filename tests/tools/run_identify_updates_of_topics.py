from pathlib import Path
from typing import Any
from unittest.mock import patch

from identify_updates_of_topics import main
from identify_updates_of_topics._utils import folder_updater
from tests.common import get_dotenv_config, get_event_with_data
from title_recognize.main import recognize_title


class LocalFileStorage(folder_updater.CloudStorage):
    path = 'build/storage/folder_hash'

    def __init__(self):
        super().__init__()
        Path(self.path).mkdir(parents=True, exist_ok=True)

    def read_folder_hash(self, snapshot_name: str) -> str:
        try:
            return (Path(self.path) / f'{snapshot_name}.txt').read_text()
        except FileNotFoundError:
            return ''

    def write_folder_hash(self, snapshot: Any, snapshot_name: str) -> None:
        (Path(self.path) / f'{snapshot_name}.txt').write_text(str(snapshot))


def fake_publish_to_pubsub(topic, message):
    print(f'Publishing to Pub/Sub topic: {topic}, message: {message}')


def fake_recognize_title_via_api(title: str, status_only: bool):
    reco_data = recognize_title(title, False)
    return {'status': 'ok', 'recognition': reco_data}


if __name__ == '__main__':
    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        patch('_dependencies.pubsub.publish_to_pubsub', fake_publish_to_pubsub),
        patch('identify_updates_of_topics._utils.forum.publish_to_pubsub', fake_publish_to_pubsub),
        patch.object(main, 'publish_to_pubsub', fake_publish_to_pubsub),
        patch.object(folder_updater, 'CloudStorage', LocalFileStorage),
        patch.object(folder_updater, 'recognize_title_via_api', fake_recognize_title_via_api),
    ):
        folders = [(276, None)]
        data = get_event_with_data(str(folders))
        main.main(data, '')
