import pytest

from send_debug_to_admin import main
from tests.common import run_smoke


def test_process_pubsub_message():
    res = run_smoke(main.process_pubsub_message)
    pass


def test_send_message():
    res = run_smoke(main.send_message)
    pass
