import datetime
from functools import lru_cache
from pathlib import Path
from random import randint
from typing import Any
from unittest.mock import Mock, patch

from dotenv import load_dotenv

from _dependencies.commons import AppConfig
from check_topics_by_upd_time import main
from tests.common import get_event_with_data


@lru_cache
def get_dotenv_config() -> AppConfig:
    assert load_dotenv('.env', override=True)
    return AppConfig()


class LocalFileStorage(main.CloudStorage):
    path = 'build/storage'

    def _read_snapshot(self, snapshot_name: str) -> str:
        try:
            return (Path(self.path) / f'{snapshot_name}.txt').read_text()
        except FileNotFoundError:
            return ''

    def _write_snapshot(self, snapshot: Any, snapshot_name: str) -> None:
        (Path(self.path) / f'{snapshot_name}.txt').write_text(str(snapshot))


def fake_publish_to_pubsub(topic, message):
    print(f'Publishing to Pub/Sub topic: {topic}, message: {message}')


if __name__ == '__main__':
    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        patch.object(main, 'CloudStorage', LocalFileStorage),
        patch.object(main, 'publish_to_pubsub', fake_publish_to_pubsub),
    ):
        # main.main(get_event_with_data(str(generate_random_param())), '')
        main.main('', '')
