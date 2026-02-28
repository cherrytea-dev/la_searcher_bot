import datetime
from contextlib import suppress
from random import randint
from unittest.mock import MagicMock, patch

import pytest
from polyfactory.factories import DataclassFactory
from sqlalchemy.engine import Connection

from _dependencies.telegram_api_wrapper import TGApiBase
from send_notifications import main
from tests.common import find_model, get_event_with_data
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
        patch('send_notifications.main.SCRIPT_SOFT_TIMEOUT_SECONDS', 10),
        patch('send_notifications.main.SLEEP_TIME_FOR_NEW_NOTIFS_RECHECK_SECONDS', 0.1),
    ):
        yield


@pytest.fixture(scope='session')
def db_client():
    yield main.db()


class TestDBClient:
    def test_get_change_log_update_time(self, db_client: main.DBClient):
        db_client.get_change_log_update_time(1)

    def test_save_sending_status_to_notif_by_user(self, db_client: main.DBClient):
        db_client.save_sending_status_to_notif_by_user(1, 'cancelled')

    def test_check_for_number_of_notifs_to_send(self, db_client: main.DBClient):
        NotSentNotificationFactory.create_batch_sync(3)
        result = db_client.check_for_number_of_notifs_to_send()
        assert result >= 3  # Could be more if other tests created notifications

    def test_save_sending_status_updates_correct_status(self, db_client: main.DBClient):
        notification = NotSentNotificationFactory.create_sync()
        db_client.save_sending_status_to_notif_by_user(notification.message_id, 'completed')

        updated = find_model(get_session(), NotifByUser, message_id=notification.message_id)
        assert updated.completed is not None
        assert updated.cancelled is None
        assert updated.failed is None

    def test_get_change_log_update_time_returns_none_for_invalid_id(self, db_client: main.DBClient):
        result = db_client.get_change_log_update_time(999)
        assert result is None


def test_main_no_message():
    with patch('send_notifications.main.DBClient.get_notifs_to_send', MagicMock(return_value=[])):
        main.main(get_event_with_data('123'), MagicMock(event_id=1))
    assert True


@pytest.mark.xdist_group(name='send_notifications')
def test_iterate_over_notifications():
    time_analytics = TimeAnalyticsFactory.build()

    session = get_session()
    doubling_notification_1, doubling_notification_2 = NotSentNotificationFactory.create_batch_sync(
        2,
        change_log_id=randint(0, 1000),
        user_id=randint(0, 1000),
    )
    unique_notification = NotSentNotificationFactory.create_sync()
    # TODO don't know why, but if move creation of unique_notification upper, then test started to fail

    with patch.object(TGApiBase, '_process_response_of_api_call', MagicMock(return_value='completed')):
        main.iterate_over_notifications(MagicMock(), 1, time_analytics)

    session.flush()

    unique_notification = session.query(NotifByUser).get(unique_notification.message_id)
    doubling_notification_1 = session.query(NotifByUser).get(doubling_notification_1.message_id)
    doubling_notification_2 = session.query(NotifByUser).get(doubling_notification_2.message_id)

    assert not unique_notification.cancelled
    assert not unique_notification.failed
    assert unique_notification.completed
    assert bool(doubling_notification_1.cancelled) ^ bool(doubling_notification_2.cancelled)  # TODO merge test


@pytest.mark.xdist_group(name='send_notifications')
def test_check_for_notifs_to_send():
    unique_notification = NotSentNotificationFactory.create_sync()
    doubling_notification_1, doubling_notification_2 = NotSentNotificationFactory.create_batch_sync(
        2,
        change_log_id=randint(0, 1000),
        user_id=randint(0, 1000),
    )

    doubling_messages = main.db().get_notifs_to_send(True)
    doubling_message_ids = [x.message_id for x in doubling_messages]
    unique_messages = main.db().get_notifs_to_send(False)
    unique_message_ids = [x.message_id for x in unique_messages]

    assert doubling_notification_1.message_id in doubling_message_ids
    assert doubling_notification_2.message_id in doubling_message_ids

    assert doubling_notification_1.message_id not in unique_message_ids
    assert doubling_notification_2.message_id not in unique_message_ids

    assert unique_notification.message_id in unique_message_ids
    assert unique_notification.message_id not in doubling_message_ids


def test_finish_time_analytics():
    time_analytics = main.TimeAnalytics(
        delays=[1],
        notif_times=[1, 2],
        parsed_times=[1, 2, 3],
        script_start_time=datetime.datetime.now(),
    )
    main.finish_time_analytics(time_analytics, list_of_change_ids=[1])


def test__process_message_sending(connection: Connection):
    main._process_message_sending(
        tg_api=MagicMock(),
        time_analytics=TimeAnalyticsFactory.build(),
        set_of_change_ids=set(),
        message_to_send=NotSentNotificationFactory.create_sync(),
    )


def test_send_single_message():
    msg = MessageFactory.build()
    tg_api = TGApiBase('token')
    with patch.object(TGApiBase, 'send_message', MagicMock(return_value='completed')):
        res = main.send_single_message(tg_api, msg)
    assert res == 'completed'


@pytest.mark.xdist_group(name='send_notifications')
def test_get_notifications_1():
    notif_failed_now = NotSentNotificationFactory.create_sync(
        failed=datetime.datetime.now(),
    )
    notif_failed_six_minutes_ago = NotSentNotificationFactory.create_sync(
        failed=datetime.datetime.now() - datetime.timedelta(minutes=6),
    )

    messages = main.db().get_notifs_to_send(select_doubling=False)

    assert not any(x.message_id == notif_failed_now.message_id for x in messages)
    assert any(x.message_id == notif_failed_six_minutes_ago.message_id for x in messages)


@pytest.mark.skip(reason='performance test')
class TestPerformance:
    def test_generate_message_batch(self):
        for _ in range(1000):
            with suppress(Exception):
                # cant set unique mailing_id
                NotSentNotificationFactory.create_sync()

    @pytest.mark.parametrize('batch_size', [1, 10, 100])
    def test_queries_performance(self, benchmark, batch_size: int, connection: Connection):
        # benchmark something

        with patch('send_notifications.main.MESSAGES_BATCH_SIZE', batch_size):
            benchmark(main.get_notifs_to_send, connection, True)
