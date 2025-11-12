import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)


class FunctionLockError(Exception):
    pass


@contextmanager
def lock_manager(conn: Connection, func_name: str, timeout_in_seconds: int) -> Iterator[None]:
    """Context manager to avoid situation when many instances running one function"""

    logger.info(f'Trying to lock function {func_name}')
    if _check_if_another_function_is_running(conn, func_name, timeout_in_seconds):
        logger.warning('Lock failed: another function is in progress')
        raise FunctionLockError()

    record_id = _write_function_start(conn, func_name)

    if _check_if_another_function_is_running(conn, func_name, timeout_in_seconds, record_id):
        logger.warning('Lock failed: another function started in same time, cancelling current.')
        _write_function_finish(conn, func_name, record_id)
        raise FunctionLockError()

    logger.info(f'Lock for function {func_name} is acuqired; {record_id=}')

    yield None

    logger.info(f'Releasing function {func_name}')
    _write_function_finish(conn, func_name, record_id)
    logger.info(f'Lock for function {func_name} is released')


def _check_if_another_function_is_running(
    conn: Connection, func_name: str, timeout_in_seconds: int, current_run_id: int = 0
) -> bool:
    now = datetime.now()
    txt = text("""
                    SELECT 
                        id 
                    FROM
                        functions_registry
                    WHERE
                        time_start > :time_start AND
                        time_finish IS NULL AND
                        id != :current_run_id AND
                        cloud_function_name  = :func_name
                    LIMIT 1
                    ;""")

    start_time = now - timedelta(seconds=timeout_in_seconds)
    res = conn.execute(txt, time_start=start_time, func_name=func_name, current_run_id=current_run_id)

    rows = list(res)
    return bool(rows)


def _write_function_start(conn: Connection, func_name: str) -> int:
    sql_text = text("""
                        INSERT INTO 
                            functions_registry
                        (time_start, cloud_function_name)
                        VALUES
                        (:start_time, :func_name )
                        RETURNING id;
                        ;
                            """)
    res = conn.execute(sql_text, func_name=func_name, start_time=datetime.now())
    return res.first()[0]


def _write_function_finish(conn: Connection, func_name: str, record_id: int) -> None:
    sql_text = text("""
                        UPDATE
                            functions_registry
                        SET
                            time_finish = :finish_time
                        WHERE
                            id=:record_id
                        ;
                    """)
    conn.execute(sql_text, record_id=record_id, finish_time=datetime.now())
