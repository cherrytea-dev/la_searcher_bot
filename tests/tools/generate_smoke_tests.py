"""
Tool for generating smoke testcases
"""

import importlib
import inspect
import re
import subprocess
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
    for dir_name in dir_names:
        if dir_name.startswith('_'):
            continue
        module = importlib.import_module(f'{dir_name}.main')
        _generate_test_cases_for_module(
            module,
            dir_name,
            f'tests/smoke/test_{dir_name}_generated.py',
        )


def _generate_test_cases_for_module(module, module_name: str, res_filename: str) -> str:
    """generate test cases for all functions in module"""

    module_lines = [
        'import pytest',
        'from tests.common import run_smoke',
        f'from {module_name} import main',
    ]

    template_ok = """
def test_{func_name}():
    res = run_smoke(main.{func_name})
    pass
        
    """
    covered_functions = get_covered_functions()

    members = inspect.getmembers(module)
    for member_name, member in members:
        if not inspect.isfunction(member):
            continue
        if member.__module__ != module.__name__:
            # don't test imported functions
            continue
        if f'{module_name}.main.{member_name}' in covered_functions:
            continue

        args_str = _generate_call_signature(member)

        testcase = template_ok.format(module_name=module_name, func_name=member_name, args=args_str)
        module_lines.append(testcase)

    Path(res_filename).write_text('\n'.join(module_lines))
    return '\n'.join(module_lines)


def _generate_call_signature(member):
    signature = inspect.signature(member)

    args = []
    for param_name in signature.parameters:
        arg_value = _get_default_arg_value(signature.parameters[param_name])
        args.append(f'{param_name}={arg_value}')

    args_str = ', '.join(args)
    return args_str


def _get_default_arg_value(param) -> str:
    if param._annotation is str:
        return "'foo'"
    elif param._annotation is int:
        return '1'
    elif param._annotation is list:
        return '[]'
    elif param._annotation is dict:
        return '{}'
    elif param._annotation is bool:
        return 'False'
    elif param._annotation is datetime:
        return 'datetime.now()'
    elif param._annotation is date:
        return 'date.today()'
    else:
        return 'MagicMock()'


@lru_cache
def get_covered_functions() -> set[str]:
    # set of functions that already covered by normal tests
    KEYWORD = 'NO SMOKE TEST'
    covered_functions = set()
    res = subprocess.getoutput(f'grep -r "{KEYWORD}" tests')
    # test_files = [x.name for x in Path('src').rglob('test*.py')]
    for line in res.splitlines():
        parts = line.split(KEYWORD)
        if len(parts) != 2:
            continue
        covered_functions.add(parts[1].strip())

    return covered_functions


if __name__ == '__main__':
    generate_all()
