import logging
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
    timeout_in_seconds = 0  # TODO do we need it?
    fn_key = f'lock_function_{func_name}'

    logging.info(f'Trying to lock function {func_name}')
    with conn.begin() as tr:
        try:
            _set_session_timeout_for_transaction(conn, 5)
            _create_record_for_function_if_not_exists(conn, fn_key)
            # TODO need separate table for locks, not key_value_storage
            _lock_record_in_transaction(conn, fn_key)
            logging.info(f'Lock for function {func_name} ic acuqired')

            yield None

            logging.info(f'Releasing lock for function {func_name}')

            tr.commit()
            logging.info(f'Lock for function {func_name} is released')

        except (OperationalError, TimeoutError) as exc:
            logging.info(f'Function {func_name} is locked by another process')

            tr.rollback()
            logging.info(f'Lock for function {func_name}: exiting')

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
