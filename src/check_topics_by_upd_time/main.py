"""Parses the folder-tree on the forum, checking the last update time. Collects the list of leaf-level folders
which contain updates – and makes a pub/sub call for other script to parse content of these folders"""

from typing import Any

from _dependencies.common.commons import get_app_config, setup_logging
from _dependencies.common.pubsub import Ctx

setup_logging(__package__)


def main(event: dict[str, Any], context: Ctx | None = None) -> None:
    if get_app_config().forum_legacy_data_source:
        from ._legacy.main import main as legacy_main

        return legacy_main(event, context)

    # this function was removed earlier.
