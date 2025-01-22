import pytest

from identify_updates_of_folders import main
from tests.common import run_smoke


def test_decompose_folder_to_subfolders_and_searches():
    res = run_smoke(main.decompose_folder_to_subfolders_and_searches)
    pass


def test_read_snapshot_from_cloud_storage():
    res = run_smoke(main.read_snapshot_from_cloud_storage)
    pass
