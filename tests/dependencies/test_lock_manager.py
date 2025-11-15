from uuid import uuid4

import pytest

from _dependencies.commons import sqlalchemy_get_pool
from _dependencies.lock_manager import lock_manager


def test_lock():
    conn1 = sqlalchemy_get_pool(5, 5).connect()

    with lock_manager(conn1, 'some_func', 10):
        print('try to run second query in pgadmin/console/..')
