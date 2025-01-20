"""
Tool for generating smoke testcases
"""

import importlib
import inspect
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

PYTEST_LOG_FILE = 'build/pytest.log'


def generate_all():
    """
    Generate all smoke testcases
    """

    dir_names = [x.name for x in Path('src').glob('*')]
    dir_names.sort()
    print('')

    cases = dict()
    for dir_name in dir_names:
        if dir_name.startswith('_'):
            continue
        module = importlib.import_module(f'{dir_name}.main')

        _add_cases(module, dir_name, cases)

    cases = {key: value for key, value in cases.items() if len(value) > 1}
    print("-----")
    # print(cases)
    # print("-----")
    for key, value in cases.items():
        print(f"def {key}: {value}")

    # print(cases.keys())
    # print("-----")


def _add_cases(module, module_name: str, cases: dict) -> str:
    """generate test cases for all functions in module"""

    members = inspect.getmembers(module)
    for member_name, member in members:
        if not inspect.isfunction(member):
            continue
        if member.__module__ != module.__name__:
            # don't test imported functions
            continue

        used_modules: list = cases.get(member_name, list())
        used_modules.append(module_name)
        cases[member_name] = used_modules


if __name__ == '__main__':
    generate_all()
