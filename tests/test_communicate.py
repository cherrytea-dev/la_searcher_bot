from unittest.mock import patch

import pytest

from tests.common import emulated_get_secrets


@pytest.fixture
def autopatch_secrets(common_patches):
    with patch('send_debug_to_admin.main.get_secrets', emulated_get_secrets):
        yield


def test_update_and_download_list_of_regions(autopatch_secrets):
    from communicate.main import update_and_download_list_of_regions

    with pytest.raises(Exception):
        """пока так"""
        update_and_download_list_of_regions(1, 2, 3, 4, 5)
