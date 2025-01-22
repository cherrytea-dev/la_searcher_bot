from datetime import date, datetime
from tempfile import TemporaryDirectory

import pytest

from tests.common import generate_args_for_function
from tests.tools.generate_smoke_tests import _generate_call_signature, _generate_test_cases_for_module


def test_generate_signature():
    def example_func(v1: str, v2: int, v3, v4: date, v5: datetime):
        pass

    signature = _generate_call_signature(example_func)
    assert signature == "v1='foo', v2=1, v3=MagicMock(), v4=date.today(), v5=datetime.now()"


@pytest.mark.skip(reason='Enable for debug only')
def test_generate_test_cases_for_module():
    from user_provide_info import main

    with TemporaryDirectory() as temp_dir:
        _generate_test_cases_for_module(main, 'user_provide_info', temp_dir + '/main.py')
        pass


def test_generate_function_args() -> dict:
    def example_func(v1: str, v2: int, v3, v4: date, v5: datetime):
        pass

    args = generate_args_for_function(example_func)
    example_func(**args)
