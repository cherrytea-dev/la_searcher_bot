from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError, TimeoutError


class FunctionLockError(Exception):
    pass


@contextmanager
def lock_manager(conn: Connection, func_name: str, timeout_in_seconds: int) -> Iterator[None]:
    """Context manager to avoid situation when many instances running one function"""
    fn_key = f'lock_function_{func_name}'
    with conn.begin() as tr:
        try:
            _set_session_timeout_for_transaction(conn, timeout_in_seconds)
            _create_record_for_function_if_not_exists(conn, fn_key)
            # TODO need separate table for locks, not key_value_storage
            _lock_record_in_transaction(conn, fn_key)

            yield None

            tr.commit()
        except (OperationalError, TimeoutError) as exc:
            tr.rollback()
            raise FunctionLockError() from exc


def _lock_record_in_transaction(conn: Connection, fn_key: str) -> None:
    sql_text = text("""
                    SELECT * FROM key_value_storage kvs
                    WHERE kvs."key" = :func_name 
                    FOR NO KEY UPDATE
                            """)
    # TODO need separate table for locks, not key_value_storage
    conn.execute(sql_text, func_name=fn_key)


def _create_record_for_function_if_not_exists(conn: Connection, fn_key: str) -> None:
    sql_text = text("""
                    INSERT INTO key_value_storage
                    VALUES (:func_name, :any_value)
                    ON CONFLICT(key) DO NOTHING
                            """)
    conn.execute(sql_text, func_name=fn_key, any_value='{}')


def _set_session_timeout_for_transaction(conn: Connection, timeout_in_seconds: int) -> None:
    conn.execute(
        text('SET idle_in_transaction_session_timeout = :timeout'),
        timeout=f'{timeout_in_seconds}s',
    )
