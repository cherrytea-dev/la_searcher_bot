import datetime
from contextlib import suppress
from random import randint
from unittest.mock import MagicMock, patch

import pytest
from polyfactory.factories import DataclassFactory

from _dependencies.commons import sql_connect_by_psycopg2
from send_notifications import main
from tests.factories.db_factories import NotifByUserFactory, get_session
from tests.factories.db_models import NotifByUser
from tests.factories.schemas import MessageFactory


class TimeAnalyticsFactory(DataclassFactory[main.TimeAnalytics]):
    script_start_time = datetime.datetime.now()


class NotSentNotificationFactory(NotifByUserFactory):
    completed = None
    cancelled = None
    failed = None
    created = datetime.datetime.now
    message_type = 'text'


@pytest.fixture(autouse=True)
def local_patches():
    with (
        patch('send_notifications.main.publish_to_pubsub'),
        patch('send_notifications.main.SCRIPT_SOFT_TIMEOUT_SECONDS', 10),
        patch('send_notifications.main.SLEEP_TIME_FOR_NEW_NOTIFS_RECHECK_SECONDS', 0.1),
    ):
        yield


def test_main_no_message():
    # NO SMOKE TEST send_notifications.main.main
    with patch('send_notifications.main.check_for_notifs_to_send', MagicMock(return_value=[])):
        main.main(MagicMock(), 'context')
    assert True


@pytest.mark.xdist_group(name='send_notifications')
def test_iterate_over_notifications():
    # NO SMOKE TEST send_notifications.main.iterate_over_notifications
    time_analytics = TimeAnalyticsFactory.build()

    session = get_session()
    unique_notification = NotSentNotificationFactory.create_sync()
    doubling_notification_1, doubling_notification_2 = NotSentNotificationFactory.create_batch_sync(
        2,
        change_log_id=randint(0, 1000),
        user_id=randint(0, 1000),
    )

    with patch('send_notifications.main.process_response', MagicMock(return_value='completed')):
        main.iterate_over_notifications(MagicMock(), 1, time_analytics)

    session.flush()

    unique_notification = session.query(NotifByUser).get(unique_notification.message_id)
    doubling_notification_1 = session.query(NotifByUser).get(doubling_notification_1.message_id)
    doubling_notification_2 = session.query(NotifByUser).get(doubling_notification_2.message_id)

    assert unique_notification.completed
    assert bool(doubling_notification_1.cancelled) ^ bool(doubling_notification_2.cancelled)


@pytest.mark.xdist_group(name='send_notifications')
def test_check_for_notifs_to_send():
    unique_notification = NotSentNotificationFactory.create_sync()
    doubling_notification_1, doubling_notification_2 = NotSentNotificationFactory.create_batch_sync(
        2,
        change_log_id=randint(0, 1000),
        user_id=randint(0, 1000),
    )

    with sql_connect_by_psycopg2() as conn, conn.cursor() as cur:
        doubling_messages = main.check_for_notifs_to_send(cur, True)
        doubling_message_ids = [x.message_id for x in doubling_messages]
        unique_messages = main.check_for_notifs_to_send(cur, False)
        unique_message_ids = [x.message_id for x in unique_messages]

        assert doubling_notification_1.message_id in doubling_message_ids
        assert doubling_notification_2.message_id in doubling_message_ids

        assert doubling_notification_1.message_id not in unique_message_ids
        assert doubling_notification_2.message_id not in unique_message_ids

        assert unique_notification.message_id in unique_message_ids
        assert unique_notification.message_id not in doubling_message_ids


def test_finish_time_analytics():
    # NO SMOKE TEST send_notifications.main.finish_time_analytics

    time_analytics = main.TimeAnalytics(
        delays=[1],
        notif_times=[1, 2],
        parsed_times=[1, 2, 3],
        script_start_time=datetime.datetime.now(),
    )
    main.finish_time_analytics(time_analytics, list_of_change_ids=[1])


def test__process_message_sending():
    # NO SMOKE TEST send_notifications.main._process_message_sending
    changed_ids = set()
    with sql_connect_by_psycopg2() as conn:
        res = main._process_message_sending(
            MagicMock(), TimeAnalyticsFactory.build(), set(), conn, NotSentNotificationFactory.create_sync()
        )
    assert not changed_ids


def test_send_single_message():
    # NO SMOKE TEST send_notifications.main.send_single_message
    msg = MessageFactory.build()
    res = main.send_single_message('foo', msg, MagicMock())
    assert res == 'completed'


@pytest.mark.skip(reason='performance test')
class TestPerformance:
    def test_generate_message_batch(self):
        for _ in range(1000):
            with suppress(Exception):
                # cant set unique mailing_id
                NotSentNotificationFactory.create_sync()

    @pytest.mark.parametrize('batch_size', [1, 10, 100])
    def test_queries_performance(self, benchmark, batch_size: int):
        # benchmark something

        with patch('send_notifications.main.MESSAGES_BATCH_SIZE', batch_size):
            with sql_connect_by_psycopg2() as conn, conn.cursor() as cur:
                benchmark(main.check_for_notifs_to_send, cur, True)
