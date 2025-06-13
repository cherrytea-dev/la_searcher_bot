import datetime
import json
import logging

import sqlalchemy
from sqlalchemy.engine import Engine

from _dependencies.pubsub import Ctx


def _check_if_other_functions_are_working(func_name: str, interval_seconds: int, pool: Engine) -> bool:
    """Check in PSQL in there's the same function 'send_notifications' working in parallel"""

    with pool.connect() as conn:
        result = conn.execute(
            sqlalchemy.text("""
                SELECT 
                    event_id 
                FROM
                    functions_registry
                WHERE
                    time_start > NOW() - interval :interval_seconds AND
                    time_finish IS NULL AND
                    cloud_function_name = :func_name
                /*action='check_if_there_is_parallel_notif_function' */
                """),
            {'interval_seconds': f'{interval_seconds} seconds', 'func_name': func_name},
        )
        parallel_functions_are_running = bool(result.scalar())

    if parallel_functions_are_running:
        logging.warning(f'Parallel functions are running. {func_name=}')

    return parallel_functions_are_running


def _record_start_of_function(
    event_num: int, function_num: int, triggered_by_func_num: int, function_name: str, pool: Engine
) -> None:
    """Record into PSQL that this function started working (id = id of the respective pub/sub event)"""
    with pool.connect() as conn:
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO 
                    functions_registry
                (event_id, time_start, cloud_function_name, function_id, triggered_by_func_id)
                VALUES
                (:event_num, :time_now, :func_name, :func_num, :triggered_by)
                /*action='save_start_of_notif_function' */
                """),
            {
                'event_num': event_num,
                'time_now': datetime.datetime.now(),
                'func_name': function_name,
                'func_num': function_num,
                'triggered_by': triggered_by_func_num,
            },
        )
        logging.info(f'function was triggered by event {event_num}, we assigned a function_id = {function_num}')


def _record_finish_of_function(event_num: int, list_of_changed_ids: list, pool: Engine) -> None:
    """Record into PSQL that this function finished working (id = id of the respective pub/sub event)"""

    with pool.connect() as conn:
        json_of_params = json.dumps({'ch_id': list_of_changed_ids})
        conn.execute(
            sqlalchemy.text("""
                UPDATE 
                    functions_registry
                SET
                    time_finish = :time_now,
                    params = :params
                WHERE
                    event_id = :event_num
                /*action='save_finish_of_notif_function' */
                """),
            {'time_now': datetime.datetime.now(), 'params': json_of_params, 'event_num': event_num},
        )


def check_and_save_event_id(
    pool: Engine,
    context: Ctx,
    event: str,
    function_id: int,
    list_of_change_log_ids: list[int] | None,
    triggered_by_func_id: int | None,
    func_name: str,
    interval: int,
) -> bool:
    """Work with PSQL table functions_registry. Goal of the table & function is to avoid parallel work of
    two compose_notifications functions. Executed in the beginning and in the end of compose_notifications function"""
    # TODO try decompose
    if not context or not event:
        return False

    event_id = context.event_id

    # if this functions is triggered in the very beginning of the Google Cloud Function execution
    if event == 'start':
        if _check_if_other_functions_are_working(func_name, interval, pool):
            _record_start_of_function(event_id, function_id, triggered_by_func_id, func_name, pool)  # type: ignore[arg-type]
            return True

        _record_start_of_function(event_id, function_id, triggered_by_func_id, func_name, pool)  # type: ignore[arg-type]
        return False

    # if this functions is triggered in the very end of the Google Cloud Function execution
    elif event == 'finish':
        _record_finish_of_function(event_id, list_of_change_log_ids or [], pool)
        return False
    return False
