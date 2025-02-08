import pytest

from send_notifications import main
from tests.common import run_smoke


def test__process_doubling_messages():
    res = run_smoke(main._process_doubling_messages)
    pass


def test__process_logs_with_completed_sending():
    res = run_smoke(main._process_logs_with_completed_sending)
    pass


def test_check_for_notifs_to_send():
    res = run_smoke(main.check_for_notifs_to_send)
    pass


def test_check_for_number_of_notifs_to_send():
    res = run_smoke(main.check_for_number_of_notifs_to_send)
    pass


def test_seconds_between():
    res = run_smoke(main.seconds_between)
    pass


def test_seconds_between_round_2():
    res = run_smoke(main.seconds_between_round_2)
    pass


def test_time_is_out():
    res = run_smoke(main.time_is_out)
    pass
