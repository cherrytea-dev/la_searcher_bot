import _dependencies.cloud_func_parallel_guard
from tests.common import run_smoke


def test_check_if_other_functions_are_working():
    res = run_smoke(_dependencies.cloud_func_parallel_guard.check_if_other_functions_are_working)
    pass


def test_check_record_start_of_function():
    res = run_smoke(_dependencies.cloud_func_parallel_guard.record_start_of_function)
    pass


def test_record_finish_of_function():
    res = run_smoke(_dependencies.cloud_func_parallel_guard.record_finish_of_function)
    pass
