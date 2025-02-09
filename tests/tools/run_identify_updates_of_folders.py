import datetime
from functools import lru_cache
from random import randint
from unittest.mock import Mock, patch

from dotenv import load_dotenv

from _dependencies.commons import AppConfig
from identify_updates_of_folders import main
from tests.common import get_event_with_data


@lru_cache
def get_dotenv_config() -> AppConfig:
    assert load_dotenv('.env', override=True)
    return AppConfig()


def read_snapshot_from_cloud_storage_mocked(*args, **kwargs):
    return str(generate_random_param())


def generate_random_param():
    folder_num = randint(1, 10000)
    return [
        [
            folder_num,
            str(datetime.datetime.now()),
            '',
            # datetime.datetime.now(),
        ],
    ]


if __name__ == '__main__':
    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        patch('_dependencies.commons.get_publisher'),
        patch('_dependencies.commons.get_project_id'),
        patch('_dependencies.commons._send_topic'),
        patch.object(main, 'read_snapshot_from_cloud_storage', read_snapshot_from_cloud_storage_mocked),
        patch.object(main, 'write_snapshot_to_cloud_storage'),
    ):
        param = f'"{generate_random_param()}"'
        main.main(get_event_with_data(str(generate_random_param())), '')
