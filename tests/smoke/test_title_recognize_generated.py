import pytest

from tests.common import run_smoke
from title_recognize import main


def test_get_requested_title():
    res = run_smoke(main.get_requested_title)
    pass


def test_main():
    res = run_smoke(main.main)
    pass


def test_recognize_title():
    res = run_smoke(main.recognize_title)
    pass
