from time import sleep
from uuid import uuid4

import pytest

from _dependencies.commons import sqlalchemy_get_pool
from _dependencies.lock_manager import FunctionLockError, lock_manager

TIMEOUT = 1


class TestFunctionsLock:
    @pytest.fixture
    def func_name(self) -> str:
        return uuid4().hex[:30]

    @pytest.fixture
    def connection(self) -> str:
        return sqlalchemy_get_pool(1, 1).connect()

    def test_is_locked(self, connection, func_name: str):
        with lock_manager(connection, func_name, TIMEOUT):
            with pytest.raises(FunctionLockError):
                with lock_manager(connection, func_name, TIMEOUT):
                    print('should fail')

    def test_is_released_after_done(self, connection, func_name: str):
        with lock_manager(connection, func_name, TIMEOUT):
            print('ok')

        sleep(TIMEOUT)
        with lock_manager(connection, func_name, TIMEOUT):
            print('ok')

    def test_is_released_by_timeout(self, connection, func_name: str):
        with lock_manager(connection, func_name, TIMEOUT):
            sleep(TIMEOUT)
            with lock_manager(connection, func_name, TIMEOUT):
                print('should be done')
