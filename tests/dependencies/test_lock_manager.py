from time import sleep
from typing import Generator
from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine

from _dependencies.common.lock_manager import FunctionLockError, lock_manager

TIMEOUT = 1


class TestFunctionsLock:
    @pytest.fixture
    def func_name(self) -> str:
        return uuid4().hex[:30]

    @pytest.fixture(autouse=True)
    def _engine(self, connection_pool: Engine) -> Generator[None, None, None]:
        self.engine = connection_pool
        yield

    def test_is_locked(self, func_name: str):
        with lock_manager(self.engine, func_name, TIMEOUT):
            with pytest.raises(FunctionLockError):
                with lock_manager(self.engine, func_name, TIMEOUT):
                    print('should fail')

    def test_is_released_after_done(self, func_name: str):
        with lock_manager(self.engine, func_name, TIMEOUT):
            print('ok')

        sleep(TIMEOUT)
        with lock_manager(self.engine, func_name, TIMEOUT):
            print('ok')

    def test_is_released_by_timeout(self, func_name: str):
        with lock_manager(self.engine, func_name, TIMEOUT):
            sleep(TIMEOUT)
            with lock_manager(self.engine, func_name, TIMEOUT):
                print('should be done')
