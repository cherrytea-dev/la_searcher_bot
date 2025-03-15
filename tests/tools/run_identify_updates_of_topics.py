import datetime
from functools import lru_cache
from pathlib import Path
from random import randint
from typing import Any
from unittest.mock import Mock, patch

from dotenv import load_dotenv

from _dependencies.commons import AppConfig
from identify_updates_of_topics import main
from identify_updates_of_topics._utils import folder_updater
from tests.common import get_event_with_data
from title_recognize.main import recognize_title


@lru_cache
def get_dotenv_config() -> AppConfig:
    assert load_dotenv('.env', override=True)
    return AppConfig()


class LocalFileStorage(folder_updater.CloudStorage):
    path = 'build/storage/folder_hash'

    def read_folder_hash(self, snapshot_name: str) -> str:
        try:
            return (Path(self.path) / f'{snapshot_name}.txt').read_text()
        except FileNotFoundError:
            return ''

    def write_folder_hash(self, snapshot: Any, snapshot_name: str) -> None:
        (Path(self.path) / f'{snapshot_name}.txt').write_text(str(snapshot))


def fake_publish_to_pubsub(topic, message):
    print(f'Publishing to Pub/Sub topic: {topic}, message: {message}')


def fake_api_call(function: str, data: dict):
    reco_data = recognize_title(data['title'], None)
    return {'status': 'ok', 'recognition': reco_data}


if __name__ == '__main__':
    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        patch('_dependencies.misc.publish_to_pubsub', fake_publish_to_pubsub),
        patch('identify_updates_of_topics._utils.forum.publish_to_pubsub', fake_publish_to_pubsub),
        patch.object(main, 'publish_to_pubsub', fake_publish_to_pubsub),
        patch.object(folder_updater, 'CloudStorage', LocalFileStorage),
        patch.object(folder_updater, 'make_api_call', fake_api_call),
        # patch.object(main, 'notify_admin', lambda x: print(f'Admin notification: {x}')),
    ):
        folders = [(276, None)]
        data = get_event_with_data(str(folders))
        # main.main(get_event_with_data(str(generate_random_param())), '')
        main.main(data, '')
