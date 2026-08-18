from typing import Generator
from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine

from _dependencies.common.lock_manager import FunctionLockError, lock_manager


class TestFunctionsLock:
    @pytest.fixture
    def func_name(self) -> str:
        return uuid4().hex[:30]

    @pytest.fixture(autouse=True)
    def _engine(self, connection_pool: Engine) -> Generator[None, None, None]:
        self.engine = connection_pool
        yield

    def test_is_locked_while_held(self, func_name: str):
        """Second acquisition attempt must fail while the lock is held."""
        with lock_manager(self.engine, func_name):
            with pytest.raises(FunctionLockError):
                with lock_manager(self.engine, func_name):
                    print('should fail')

    def test_is_released_after_done(self, func_name: str):
        """The lock must be free again immediately after the context exits."""
        with lock_manager(self.engine, func_name):
            print('ok')

        with lock_manager(self.engine, func_name):
            print('ok')

    def test_is_released_on_exception(self, func_name: str):
        """The lock must be released even if the body raises."""
        with pytest.raises(RuntimeError):
            with lock_manager(self.engine, func_name):
                raise RuntimeError('boom')

        # no timeout / sleep needed — advisory lock is freed on connection close
        with lock_manager(self.engine, func_name):
            print('ok after exception')

    def test_different_functions_do_not_block(self):
        """Two different func_names must not contend for the same lock."""
        with lock_manager(self.engine, 'fn_a'):
            with lock_manager(self.engine, 'fn_b'):
                print('both held')
