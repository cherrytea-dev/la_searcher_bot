"""compose and save all the text / location messages, then initiate sending via pub-sub"""

import datetime
import logging

from _dependencies.common.commons import setup_logging
from _dependencies.common.lock_manager import FunctionLockError, lock_manager
from _dependencies.common.misc import generate_random_function_id
from _dependencies.common.pubsub import Ctx, pubsub_compose_notifications

from ._utils.commons import LineInChangeLog, User
from ._utils.database import DBClient
from ._utils.log_record_composer import LogRecordComposer
from ._utils.notifications_maker import NotificationMaker
from ._utils.users_list_composer import UserListFilter, UsersListComposer

INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS = 250
FUNC_NAME = 'compose_notifications'


setup_logging(__package__)


def call_self_if_need_compose_more(db: DBClient, function_id: int) -> None:
    """check if there are any notifications remained to be composed"""

    if db.has_uncomposed_notifications():
        logging.info('we checked – there is still something to compose: re-initiating [compose_notification]')
        pubsub_compose_notifications(function_id, 're-run from same script')
    else:
        logging.info('we checked – there is nothing to compose: we are not re-initiating [compose_notification]')


def create_user_notifications_from_change_log_record(
    analytics_start_of_func: datetime.datetime,
    function_id: int,
    db: DBClient,
    new_record: LineInChangeLog,
    list_of_users: list[User],
) -> datetime.datetime:
    analytics_match_finish = datetime.datetime.now()
    duration_match = round((analytics_match_finish - analytics_start_of_func).total_seconds(), 2)
    logging.info(f'time: function match end-to-end – {duration_match} sec')

    # Mark change_log as "in progress" BEFORE inserting notif_by_user records.
    # This prevents a second compose_notifications instance from picking up
    # the same change_log_id if the lock expires or YMQ redelivers the message.
    db.mark_change_log_in_progress(new_record.change_log_id)
    logging.info(f'change_log {new_record.change_log_id} marked as in-progress (s)')

    # check the matrix: new update - user and initiate sending notifications
    notification_maker = NotificationMaker(db, new_record, list_of_users)
    notification_maker.generate_notifications_for_users(function_id)

    analytics_iterations_finish = datetime.datetime.now()
    duration_iterations = round((analytics_iterations_finish - analytics_match_finish).total_seconds(), 2)
    logging.info(f'time: function iterations end-to-end – {duration_iterations} sec')

    # mark all the "new" lines in tables Change Log & Comments as "old"
    notification_maker.mark_new_record_as_processed()
    notification_maker.mark_new_comments_as_processed()

    # final step – update statistics on how many users received notifications on new searches
    notification_maker.record_notification_statistics()
    return analytics_iterations_finish  # TODO can we move it out of this function?


def main(event: dict, context: Ctx) -> None:
    """key function which is initiated by Pub/Sub"""

    analytics_start_of_func = datetime.datetime.now()

    function_id = generate_random_function_id()

    db = DBClient()
    new_record: LineInChangeLog | None = None
    analytics_iterations_finish: datetime.datetime | None = None
    try:
        with lock_manager(db._db, FUNC_NAME, INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS):
            # compose New Records List: the delta from Change log
            new_record = LogRecordComposer(db).get_line()

            if new_record:
                list_of_users = UsersListComposer(db).get_users_list_for_line_in_change_log(new_record)
                list_of_users = UserListFilter(db, new_record, list_of_users).apply()

                analytics_iterations_finish = create_user_notifications_from_change_log_record(
                    analytics_start_of_func,
                    function_id,
                    db,
                    new_record,
                    list_of_users,
                )

            call_self_if_need_compose_more(db, function_id)
    except FunctionLockError:
        logging.info('function execution stopped due to parallel run with another function')
        logging.info('script cancelled')
        return

    analytics_finish = datetime.datetime.now()
    if new_record and analytics_iterations_finish:
        duration_saving = round((analytics_finish - analytics_iterations_finish).total_seconds(), 2)
        logging.info(f'time: function data saving – {duration_saving} sec')

    duration_full = round((analytics_finish - analytics_start_of_func).total_seconds(), 2)
    logging.info(f'time: function full end-to-end – {duration_full} sec')

    logging.info('script finished')
