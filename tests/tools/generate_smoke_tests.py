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
    for dir_name in dir_names:
        if dir_name.startswith('_'):
            continue
        module = importlib.import_module(f'{dir_name}.main')
        _generate_test_cases_for_module(
            module,
            dir_name,
            f'tests/smoke/test_{dir_name}_generated.py',
        )


@lru_cache
def _extract_broken_testscases_from_pytest_log() -> list[tuple[str, str, str]]:
    pytest_out = Path(PYTEST_LOG_FILE).read_text()

    res = []
    exp = re.compile('FAILED(.*)\.py::(\w*)( .*)*$')
    for line in pytest_out.splitlines():
        if not line.strip().startswith('FAILED'):
            continue
        try:
            test_module_name, test_case_name, tail_ = exp.findall(line)[0]
            test_module_name = test_module_name.split('/')[-1]
            res.append((test_module_name, test_case_name))
        except:
            pass
    return res


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
    template_exception = """
def test_{func_name}():
    with pytest.raises(Exception) as e:
        res = run_smoke(main.{func_name})
    pass
        
    """
    broken_test_cases = _extract_broken_testscases_from_pytest_log()
    broken_test_cases_set = set(
        [f'{test_module_name}:{test_case_name}' for test_module_name, test_case_name in broken_test_cases]
    )

    members = inspect.getmembers(module)
    for member_name, member in members:
        if not inspect.isfunction(member):
            continue
        if member.__module__ != module.__name__:
            # don't test imported functions
            continue

        args_str = _generate_call_signature(member)

        search_key = f'test_{module_name}_generated:test_{member_name}'
        template = template_ok if search_key not in broken_test_cases_set else template_exception
        testcase = template.format(module_name=module_name, func_name=member_name, args=args_str)
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


if __name__ == '__main__':
    generate_all()
