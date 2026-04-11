import datetime
from contextlib import suppress
from random import randint
from unittest.mock import MagicMock, patch

import pytest
from polyfactory.factories import DataclassFactory
from sqlalchemy.engine import Connection

from _dependencies.telegram_api_wrapper import TGApiBase
from _dependencies.vk_api_client import VKApi
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
        main.iterate_over_notifications(1, time_analytics)

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


def test_send_single_message():
    msg = MessageFactory.build()
    tg_api = TGApiBase('token')
    vk_api = VKApi('token')
    with (
        patch.object(TGApiBase, 'send_message', MagicMock(return_value='completed')),
        patch.object(VKApi, 'send', MagicMock(return_value={})),
    ):
        res = main.send_single_message(tg_api, vk_api, msg)
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


@pytest.mark.skip(reason='Real run')
class TestSendVKReal:
    def test_send_via_client(self):
        import os
        import random

        message_html = 'НЖ – изменение статуса по <a href="https://lizaalert.org/forum/viewtopic.php?t=123">Иванова ж40 лет</a> (Москва и МО – Активные поиски)'
        message_md = 'hello!\nsecond string - **bold**\n[link here](vk.com/foo)'

        apikey = os.getenv('VK_API_KEY')
        my_user_id = os.getenv('VK_USER_ID')  # TODO
        cln = VKApi(apikey)
        randint = f'{random.randint(1_000_000, 100_000_000)}'
        resp_data = cln.send(
            user_id=my_user_id,
            random_id=randint,
            # message=message_md,
            message=message_html,
            # lat='56.839356',
            # long='60.608865',
        )
        assert 'error' not in resp_data


class TestFormatMessageForVK:
    @pytest.mark.parametrize(
        'input,result',
        [
            (
                'НЖ <a href="https://lizaalert.org/forum/viewtopic.php?t=123">Иванова ж40 лет</a> (Самара)',
                'НЖ https://lizaalert.org/forum/viewtopic.php?t=123 Иванова ж40 лет (Самара)',
                # unfold links starting with lizaalert.org/forum/viewtopic.php
            ),
            (
                'Комментарии от <a href="https://lizaalert.org/forum/memberlist.php?mode=viewprofile&amp;u=107175">Странник_klg</a>:',
                'Комментарии от Странник_klg:',
                # remove whole links starting with https://lizaalert.org/forum/memberlist.php
            ),
            (
                '«<a href="https://lizaalert.org/forum/viewtopic.php?&amp;t=367030&amp;start=36">Странник_klg, в экипаже с Амрита, РВП позже   </a>',
                '«Странник_klg, в экипаже с Амрита, РВП позже   ',
                # remove whole links starting with https://lizaalert.org/forum/viewtopic.php and containing "start" in query
            ),
            (
                '<i>some text and other links</i>',
                'some text and other links',
                # remove italic
            ),
            (
                '<s>some text and other links</s>',
                'some text and other links',
                # remove strikethrough
            ),
            (
                '<b>some text and other links</b>',
                'some text and other links',
                # remove bold
            ),
            (
                ' <a href="tel:+79001234567"> ☎️+79001234567</a>»',
                '  ☎️+79001234567»',
                # remove whole link like phone numbers tel:+79001234567
            ),
            (
                '<b> <a href="tel:+79001234567"> ☎️+79001234567</a>»</b>',
                '  ☎️+79001234567»',
                # remove nested hrefs too
            ),
        ],
    )
    def test_format(self, input: str, result: str):
        assert main.format_mesage_for_vk(input) == result
