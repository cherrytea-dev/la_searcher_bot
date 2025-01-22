import pytest

from send_notifications_helper_2 import main
from tests.common import run_smoke


def test_check_first_notif_to_send():
    res = run_smoke(main.check_first_notif_to_send)
    pass


def test_check_for_notifs_to_send():
    res = run_smoke(main.check_for_notifs_to_send)
    pass


def test_iterate_over_notifications():
    res = run_smoke(main.iterate_over_notifications)
    pass


def test_send_single_message():
    res = run_smoke(main.send_single_message)
    pass
