import pytest

from manage_users import main
from tests.common import run_smoke


def test_save_default_notif_settings():
    res = run_smoke(main.save_default_notif_settings)
    pass


def test_save_new_user():
    res = run_smoke(main.save_new_user)
    pass


def test_save_onboarding_step():
    res = run_smoke(main.save_onboarding_step)
    pass
