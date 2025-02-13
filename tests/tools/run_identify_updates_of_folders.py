import datetime
from functools import lru_cache
from pathlib import Path
from random import randint
from typing import Any
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


def get_incoming_message():
    """real message from check_topics_by_upd_time"""
    return [
        [276, '2025-02-13T11:11:17+00:00'],
        [41, '2025-02-13T13:36:45+00:00'],
        [179, '2025-02-13T13:31:28+00:00'],
        [180, '2025-02-13T11:20:55+00:00'],
        [181, '2025-02-13T07:07:42+00:00'],
        [188, '2025-02-12T12:58:15+00:00'],
        [182, '2025-02-13T08:21:42+00:00'],
        [187, '2025-02-12T19:54:17+00:00'],
        [183, '2025-02-13T13:53:12+00:00'],
        [184, '2025-02-12T20:40:39+00:00'],
        [171, '2024-07-16T01:56:20+00:00'],
        [240, '2020-06-15T09:07:33+00:00'],
        [116, '2024-08-23T10:16:48+00:00'],
        [462, '2025-01-08T19:10:34+00:00'],
        [438, '2024-01-10T14:09:00+00:00'],
        [410, '2022-12-20T08:10:16+00:00'],
        [394, '2024-01-03T15:29:05+00:00'],
        [354, '2021-10-30T20:42:35+00:00'],
        [348, '2020-10-25T17:00:45+00:00'],
        [285, '2020-08-19T13:07:06+00:00'],
        [243, '2022-11-28T10:10:45+00:00'],
        [207, '2023-01-19T13:35:08+00:00'],
        [227, '2016-01-01T18:31:23+00:00'],
        [216, '2020-03-12T18:26:48+00:00'],
        [42, '2017-04-06T12:46:15+00:00'],
        [167, '2013-06-05T13:55:36+00:00'],
        [134, '2012-07-13T19:05:51+00:00'],
        [281, '2024-07-28T12:36:35+00:00'],
        [111, '2023-11-07T15:26:29+00:00'],
    ]


if __name__ == '__main__':
    with (
        patch('_dependencies.commons._get_config', get_dotenv_config),
        patch.object(main, 'CloudStorage', LocalFileStorage),
        patch.object(main, 'publish_to_pubsub', fake_publish_to_pubsub),
    ):
        # main.main(get_event_with_data(str(generate_random_param())), '')
        main.main(get_event_with_data(str(get_incoming_message())), '')
