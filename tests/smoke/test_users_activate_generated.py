import pytest

from tests.common import run_smoke
from users_activate import main


def test_main():
    res = run_smoke(main.main)
    pass


def test_mark_up_onboarding_status_0():
    res = run_smoke(main.mark_up_onboarding_status_0)
    pass


def test_mark_up_onboarding_status_0_2():
    res = run_smoke(main.mark_up_onboarding_status_0_2)
    pass


def test_mark_up_onboarding_status_10():
    res = run_smoke(main.mark_up_onboarding_status_10)
    pass


def test_mark_up_onboarding_status_10_2():
    res = run_smoke(main.mark_up_onboarding_status_10_2)
    pass


def test_mark_up_onboarding_status_20():
    res = run_smoke(main.mark_up_onboarding_status_20)
    pass


def test_mark_up_onboarding_status_21():
    res = run_smoke(main.mark_up_onboarding_status_21)
    pass


def test_mark_up_onboarding_status_80():
    res = run_smoke(main.mark_up_onboarding_status_80)
    pass


def test_mark_up_onboarding_status_80_have_all_settings():
    res = run_smoke(main.mark_up_onboarding_status_80_have_all_settings)
    pass


def test_mark_up_onboarding_status_80_just_got_summaries():
    res = run_smoke(main.mark_up_onboarding_status_80_just_got_summaries)
    pass


def test_mark_up_onboarding_status_80_patch():
    res = run_smoke(main.mark_up_onboarding_status_80_patch)
    pass


def test_mark_up_onboarding_status_80_self_deactivated():
    res = run_smoke(main.mark_up_onboarding_status_80_self_deactivated)
    pass


def test_mark_up_onboarding_status_80_wo_dialogs():
    res = run_smoke(main.mark_up_onboarding_status_80_wo_dialogs)
    pass


def test_mark_up_onboarding_status_99():
    res = run_smoke(main.mark_up_onboarding_status_99)
    pass
