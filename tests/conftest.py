import io
import urllib.request
from unittest.mock import patch

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(autouse=True)
def patch_logging():
    """
    To disable for specific tests, use next advice:
    https://stackoverflow.com/questions/38748257/disable-autouse-fixtures-on-specific-pytest-marks

    """

    with patch("google.cloud.logging.Client") as mock:
        yield mock


@pytest.fixture(autouse=True)
def common_patches():
    """
    Common patch for all tests to enable imports
    """
    with (
        patch.object(urllib.request, "urlopen") as urllib_request_mock,
        patch("google.cloud.secretmanager.SecretManagerServiceClient"),
        patch("google.cloud.pubsub_v1.PublisherClient"),
    ):
        urllib_request_mock.return_value = io.BytesIO(b"1")
        yield
