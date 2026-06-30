import datetime
import os
import random
from random import randint
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy
from polyfactory.factories import DataclassFactory
from sqlalchemy.engine import Connection

from _dependencies.bot.messenger_clients import MaxClient
from _dependencies.bot.telegram_api_wrapper import TGApiBase
from _dependencies.bot.vk_api_client import VKApi
from _dependencies.common.commons import SendResult, sqlalchemy_get_pool
from send_notifications import main
from tests.common import find_model, get_event_with_data
from tests.factories.db_factories import NotifByUserFactory, UserFactory, get_session
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


def _ensure_identity_map(conn: Connection, internal_user_id: int, messenger: str, messenger_user_id: str) -> None:
    """Insert into user_identity_map with ON CONFLICT DO NOTHING to handle stale data."""
    conn.execute(
        sqlalchemy.text("""
            INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
            VALUES (:internal_user_id, :messenger, :messenger_user_id)
            ON CONFLICT DO NOTHING
        """),
        {'internal_user_id': internal_user_id, 'messenger': messenger, 'messenger_user_id': messenger_user_id},
    )


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


# ─── Category 1: get_notifs_to_send() — messenger column ───


@pytest.mark.xdist_group(name='send_notifications')
class TestGetNotifsToSendMessenger:
    """Tests for the messenger column in get_notifs_to_send()."""

    def _insert_notification(self, messenger: str) -> int:
        """Insert a notification directly via SQL to control messenger value precisely."""
        pool = sqlalchemy_get_pool()
        user_id = randint(10_000_000, 99_999_999)
        with pool.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    INSERT INTO notif_by_user
                        (user_id, message_content, message_type, message_params, created, messenger)
                    VALUES
                        (:user_id, 'test', 'text', '{}', NOW(), :messenger)
                    RETURNING message_id
                """),
                {'user_id': user_id, 'messenger': messenger},
            )
            return result.scalar()

    def test_messenger_defaults_to_telegram(self, db_client: main.DBClient):
        """NotifByUser with messenger='telegram' → MessageToSend.messenger == 'telegram'."""
        msg_id = self._insert_notification(messenger='telegram')
        messages = db_client.get_notifs_to_send(select_doubling=False)
        match = [m for m in messages if m.message_id == msg_id]
        assert len(match) == 1
        assert match[0].messenger == 'telegram'

    def test_messenger_vk(self, db_client: main.DBClient):
        """NotifByUser with messenger='vk' → MessageToSend.messenger == 'vk'."""
        msg_id = self._insert_notification(messenger='vk')
        messages = db_client.get_notifs_to_send(select_doubling=False)
        match = [m for m in messages if m.message_id == msg_id]
        assert len(match) == 1
        assert match[0].messenger == 'vk'

    def test_messenger_mixed(self, db_client: main.DBClient):
        """Both types in one batch — each gets correct messenger."""
        tg_id = self._insert_notification(messenger='telegram')
        vk_id = self._insert_notification(messenger='vk')
        messages = db_client.get_notifs_to_send(select_doubling=False)
        tg_match = [m for m in messages if m.message_id == tg_id]
        vk_match = [m for m in messages if m.message_id == vk_id]
        assert len(tg_match) == 1
        assert len(vk_match) == 1
        assert tg_match[0].messenger == 'telegram'
        assert vk_match[0].messenger == 'vk'


# ─── Category 2: fill_vk_user_ids() — new path via user_identity_map ───


@pytest.mark.xdist_group(name='send_notifications')
class TestFillVkUserIds:
    """Tests for fill_vk_user_ids() — identity_map resolution."""

    def _make_vk_notification(self, user_id: int) -> main.MessageToSend:
        """Create a VK-destined MessageToSend (not persisted)."""
        return main.MessageToSend(
            message_id=randint(1_000_000, 9_999_999),
            user_id=user_id,
            created=datetime.datetime.now(),
            completed=None,
            cancelled=None,
            message_content='test',
            message_type='text',
            message_params='{}',
            message_group_id=None,
            change_log_id=randint(1, 9999),
            failed=None,
            vk_id=None,
            messenger='vk',
        )

    def _make_telegram_notification(self, user_id: int) -> main.MessageToSend:
        """Create a Telegram-destined MessageToSend (not persisted)."""
        return main.MessageToSend(
            message_id=randint(1_000_000, 9_999_999),
            user_id=user_id,
            created=datetime.datetime.now(),
            completed=None,
            cancelled=None,
            message_content='test',
            message_type='text',
            message_params='{}',
            message_group_id=None,
            change_log_id=randint(1, 9999),
            failed=None,
            vk_id=None,
            messenger='telegram',
        )

    def test_no_vk_messages(self, db_client: main.DBClient):
        """No VK messages → early return, vk_id stays None for all messages."""
        tg_msg = self._make_telegram_notification(user_id=12345)
        db_client.fill_vk_user_ids([tg_msg])
        assert tg_msg.vk_id is None

    def test_from_identity_map(self, db_client: main.DBClient):
        """VK message, user in user_identity_map → vk_id filled."""
        user_id = randint(10_000_000, 99_999_999)
        vk_user_id = str(randint(100_000, 999_999))
        pool = sqlalchemy_get_pool()
        with pool.connect() as conn:
            _ensure_identity_map(conn, user_id, 'vk', vk_user_id)

        msg = self._make_vk_notification(user_id=user_id)
        db_client.fill_vk_user_ids([msg])
        assert msg.vk_id == vk_user_id

    def test_not_found(self, db_client: main.DBClient):
        """VK message, user not in identity_map → vk_id stays None."""
        user_id = randint(10_000_000, 99_999_999)
        # Create user but without identity_map entry
        UserFactory.create_sync(user_id=user_id, internal_user_id=user_id, vk_id=None)

        msg = self._make_vk_notification(user_id=user_id)
        db_client.fill_vk_user_ids([msg])
        assert msg.vk_id is None

    def test_multiple_users_mixed(self, db_client: main.DBClient):
        """Multiple VK messages: some from identity_map, some not found."""
        user_a = randint(10_000_000, 99_999_999)
        user_b = randint(10_000_000, 99_999_999)
        vk_a = str(randint(100_000, 999_999))

        pool = sqlalchemy_get_pool()
        with pool.connect() as conn:
            _ensure_identity_map(conn, user_a, 'vk', vk_a)
        UserFactory.create_sync(user_id=user_b, internal_user_id=user_b, vk_id=None)

        msgs = [
            self._make_vk_notification(user_id=user_a),
            self._make_vk_notification(user_id=user_b),
        ]
        db_client.fill_vk_user_ids(msgs)
        assert msgs[0].vk_id == vk_a
        assert msgs[1].vk_id is None


# ─── Category 2b: fill_max_user_ids() — new path via user_identity_map ───


@pytest.mark.xdist_group(name='send_notifications')
class TestFillMaxUserIds:
    """Tests for fill_max_user_ids() — identity_map resolution."""

    def _make_max_notification(self, user_id: int) -> main.MessageToSend:
        """Create a MAX-destined MessageToSend (not persisted)."""
        return main.MessageToSend(
            message_id=randint(1_000_000, 9_999_999),
            user_id=user_id,
            created=datetime.datetime.now(),
            completed=None,
            cancelled=None,
            message_content='test',
            message_type='text',
            message_params='{}',
            message_group_id=None,
            change_log_id=randint(1, 9999),
            failed=None,
            vk_id=None,
            max_id=None,
            messenger='max',
        )

    def _make_telegram_notification(self, user_id: int) -> main.MessageToSend:
        """Create a Telegram-destined MessageToSend (not persisted)."""
        return main.MessageToSend(
            message_id=randint(1_000_000, 9_999_999),
            user_id=user_id,
            created=datetime.datetime.now(),
            completed=None,
            cancelled=None,
            message_content='test',
            message_type='text',
            message_params='{}',
            message_group_id=None,
            change_log_id=randint(1, 9999),
            failed=None,
            vk_id=None,
            max_id=None,
            messenger='telegram',
        )

    def test_no_max_messages(self, db_client: main.DBClient):
        """No MAX messages → early return, max_id stays None for all messages."""
        tg_msg = self._make_telegram_notification(user_id=12345)
        db_client.fill_max_user_ids([tg_msg])
        assert tg_msg.max_id is None

    def test_from_identity_map(self, db_client: main.DBClient):
        """MAX message, user in user_identity_map → max_id filled."""
        user_id = randint(10_000_000, 99_999_999)
        max_user_id = str(randint(100_000, 999_999))
        pool = sqlalchemy_get_pool()
        with pool.connect() as conn:
            _ensure_identity_map(conn, user_id, 'max', max_user_id)

        msg = self._make_max_notification(user_id=user_id)
        db_client.fill_max_user_ids([msg])
        assert msg.max_id == max_user_id

    def test_not_found(self, db_client: main.DBClient):
        """MAX message, user not in identity_map → max_id stays None."""
        user_id = randint(10_000_000, 99_999_999)
        msg = self._make_max_notification(user_id=user_id)
        db_client.fill_max_user_ids([msg])
        assert msg.max_id is None

    def test_multiple_users_mixed(self, db_client: main.DBClient):
        """Multiple MAX messages: some from identity_map, some not found."""
        user_a = randint(10_000_000, 99_999_999)
        user_b = randint(10_000_000, 99_999_999)
        max_a = str(randint(100_000, 999_999))

        pool = sqlalchemy_get_pool()
        with pool.connect() as conn:
            _ensure_identity_map(conn, user_a, 'max', max_a)

        msgs = [
            self._make_max_notification(user_id=user_a),
            self._make_max_notification(user_id=user_b),
        ]
        db_client.fill_max_user_ids(msgs)
        assert msgs[0].max_id == max_a
        assert msgs[1].max_id is None


# ─── Category 3: send_single_message() — dispatch by messenger ───


class TestSendSingleMessage:
    """Tests for send_single_message() — messenger-based dispatch."""

    def _make_msg(self, **kwargs: Any) -> main.MessageToSend:
        defaults: dict[str, Any] = dict(
            message_id=randint(1_000_000, 9_999_999),
            user_id=randint(10_000_000, 99_999_999),
            created=datetime.datetime.now(),
            completed=None,
            cancelled=None,
            message_content='test message',
            message_type='text',
            message_params='{}',
            message_group_id=None,
            change_log_id=randint(1, 9999),
            failed=None,
            vk_id=None,
            max_id=None,
            messenger='telegram',
        )
        defaults.update(kwargs)
        return main.MessageToSend(**defaults)  # type: ignore[arg-type]

    # ── VK messenger ──

    def test_vk_text(self):
        """messenger='vk', message_type='text' → calls vk_api.send() with text, returns 'completed'."""
        msg = self._make_msg(messenger='vk', message_type='text', message_content='hello vk')
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        with (
            patch.object(TGApiBase, 'send_message') as tg_mock,
            patch.object(VKApi, 'send', MagicMock(return_value={})) as vk_mock,
        ):
            res = main.send_single_message(tg_api, vk_api, msg)
        assert res == 'completed'
        vk_mock.assert_called_once()
        args, _ = vk_mock.call_args
        assert args[0] == msg.user_id  # recipient = user_id (no vk_id)
        assert 'hello vk' in args[2]  # formatted text
        tg_mock.assert_not_called()

    def test_vk_text_with_vk_id(self):
        """messenger='vk', vk_id set → uses vk_id as recipient."""
        msg = self._make_msg(messenger='vk', message_type='text', vk_id='98765')
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        with (
            patch.object(TGApiBase, 'send_message') as tg_mock,
            patch.object(VKApi, 'send', MagicMock(return_value={})) as vk_mock,
        ):
            main.send_single_message(tg_api, vk_api, msg)
        vk_mock.assert_called_once()
        args, _ = vk_mock.call_args
        assert args[0] == '98765'  # recipient = vk_id
        tg_mock.assert_not_called()

    def test_vk_coords(self):
        """messenger='vk', message_type='coords' → calls vk_api.send() with lat/long."""
        msg = self._make_msg(
            messenger='vk',
            message_type='coords',
            message_params='{"latitude": 55.75, "longitude": 37.62}',
        )
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        with (
            patch.object(TGApiBase, 'send_location') as tg_mock,
            patch.object(VKApi, 'send', MagicMock(return_value={})) as vk_mock,
        ):
            res = main.send_single_message(tg_api, vk_api, msg)
        assert res == 'completed'
        vk_mock.assert_called_once()
        _, kwargs = vk_mock.call_args
        assert kwargs.get('lat') == 55.75
        assert kwargs.get('long') == 37.62
        tg_mock.assert_not_called()

    def test_vk_unknown_type(self):
        """messenger='vk', unknown message_type → ValueError."""
        msg = self._make_msg(messenger='vk', message_type='unknown_type')
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        with (
            patch.object(TGApiBase, 'send_message'),
            patch.object(VKApi, 'send'),
        ):
            with pytest.raises(ValueError, match='unknown message_type for VK'):
                main.send_single_message(tg_api, vk_api, msg)

    def test_vk_failure(self):
        """messenger='vk', vk_api.send() raises → returns 'failed'."""
        msg = self._make_msg(messenger='vk', message_type='text')
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        with (
            patch.object(TGApiBase, 'send_message') as tg_mock,
            patch.object(VKApi, 'send', side_effect=Exception('API error')),
        ):
            res = main.send_single_message(tg_api, vk_api, msg)
        assert res == 'failed'
        tg_mock.assert_not_called()

    # ── MAX messenger ──

    def test_max_text(self):
        """messenger='max', message_type='text' → calls MaxClient.send_message() with html, returns 'completed'."""
        msg = self._make_msg(messenger='max', message_type='text', message_content='hello max')
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        max_client = MagicMock(spec=MaxClient)
        max_client.send_message.return_value = SendResult(success=True, status='completed')
        with (
            patch.object(TGApiBase, 'send_message') as tg_mock,
            patch.object(VKApi, 'send') as vk_mock,
            patch('send_notifications.main.get_default_max_client', return_value=max_client),
        ):
            res = main.send_single_message(tg_api, vk_api, msg)
        assert res == 'completed'
        max_client.send_message.assert_called_once()
        args, kwargs = max_client.send_message.call_args
        assert kwargs.get('parse_mode') == 'html'
        assert 'hello max' in args[1]  # text is the second positional arg
        tg_mock.assert_not_called()
        vk_mock.assert_not_called()

    def test_max_text_with_max_id(self):
        """messenger='max', max_id set → uses max_id as recipient."""
        msg = self._make_msg(messenger='max', message_type='text', max_id='54321')
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        max_client = MagicMock(spec=MaxClient)
        max_client.send_message.return_value = SendResult(success=True, status='completed')
        with (
            patch.object(TGApiBase, 'send_message') as tg_mock,
            patch.object(VKApi, 'send') as vk_mock,
            patch('send_notifications.main.get_default_max_client', return_value=max_client),
        ):
            main.send_single_message(tg_api, vk_api, msg)
        max_client.send_message.assert_called_once()
        args, _ = max_client.send_message.call_args
        # The UserIdentity should have messenger_user_id = '54321'
        user_identity = args[0]
        assert user_identity.messenger_user_id == '54321'
        tg_mock.assert_not_called()
        vk_mock.assert_not_called()

    def test_max_coords(self):
        """messenger='max', message_type='coords' → calls MaxClient.send_coordinates() with lat/lng."""
        msg = self._make_msg(
            messenger='max',
            message_type='coords',
            message_params='{"latitude": 55.75, "longitude": 37.62}',
        )
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        max_client = MagicMock(spec=MaxClient)
        max_client.send_coordinates.return_value = SendResult(success=True, status='completed')
        with (
            patch.object(TGApiBase, 'send_location') as tg_mock,
            patch.object(VKApi, 'send') as vk_mock,
            patch('send_notifications.main.get_default_max_client', return_value=max_client),
        ):
            res = main.send_single_message(tg_api, vk_api, msg)
        assert res == 'completed'
        max_client.send_coordinates.assert_called_once()
        _, kwargs = max_client.send_coordinates.call_args
        assert kwargs.get('lat') == 55.75
        assert kwargs.get('lng') == 37.62
        tg_mock.assert_not_called()
        vk_mock.assert_not_called()

    def test_max_unknown_type(self):
        """messenger='max', unknown message_type → ValueError."""
        msg = self._make_msg(messenger='max', message_type='unknown_type')
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        max_client = MagicMock(spec=MaxClient)
        with (
            patch.object(TGApiBase, 'send_message'),
            patch.object(VKApi, 'send'),
            patch('send_notifications.main.get_default_max_client', return_value=max_client),
        ):
            with pytest.raises(ValueError, match='unknown message_type for MAX'):
                main.send_single_message(tg_api, vk_api, msg)

    def test_max_failure(self):
        """messenger='max', MaxClient.send_message() raises → returns 'failed'."""
        msg = self._make_msg(messenger='max', message_type='text')
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        max_client = MagicMock(spec=MaxClient)
        max_client.send_message.side_effect = Exception('API error')
        with (
            patch.object(TGApiBase, 'send_message') as tg_mock,
            patch.object(VKApi, 'send') as vk_mock,
            patch('send_notifications.main.get_default_max_client', return_value=max_client),
        ):
            res = main.send_single_message(tg_api, vk_api, msg)
        assert res == 'failed'
        tg_mock.assert_not_called()
        vk_mock.assert_not_called()

    # ── Telegram messenger (default) ──

    def test_telegram_text_no_vk(self):
        """messenger='telegram', vk_id=None, message_type='text' → only tg_api.send_message()."""
        msg = self._make_msg(messenger='telegram', vk_id=None, message_type='text')
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        with (
            patch.object(TGApiBase, 'send_message', MagicMock(return_value='completed')) as tg_mock,
            patch.object(VKApi, 'send') as vk_mock,
        ):
            res = main.send_single_message(tg_api, vk_api, msg)
        assert res == 'completed'
        tg_mock.assert_called_once()
        vk_mock.assert_not_called()

    def test_telegram_coords_no_vk(self):
        """messenger='telegram', vk_id=None, message_type='coords' → only tg_api.send_location()."""
        msg = self._make_msg(
            messenger='telegram',
            vk_id=None,
            message_type='coords',
            message_params='{"latitude": 55.75, "longitude": 37.62}',
        )
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        with (
            patch.object(TGApiBase, 'send_location', MagicMock(return_value='completed')) as tg_mock,
            patch.object(VKApi, 'send') as vk_mock,
        ):
            res = main.send_single_message(tg_api, vk_api, msg)
        assert res == 'completed'
        tg_mock.assert_called_once_with(msg.user_id, 55.75, 37.62)
        vk_mock.assert_not_called()

    def test_telegram_unknown_type(self):
        """messenger='telegram', unknown message_type → ValueError."""
        msg = self._make_msg(messenger='telegram', message_type='unknown_type')
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        with (
            patch.object(TGApiBase, 'send_message'),
            patch.object(VKApi, 'send'),
        ):
            with pytest.raises(ValueError, match='unknown message_type'):
                main.send_single_message(tg_api, vk_api, msg)

    # ── Edge cases ──

    def test_truncates_long_text(self):
        """message_content > 3000 chars → truncated to 1500 + ... + 1000."""
        long_text = 'A' * 4000
        msg = self._make_msg(messenger='telegram', message_content=long_text)
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        with (
            patch.object(TGApiBase, 'send_message', MagicMock(return_value='completed')) as tg_mock,
            patch.object(VKApi, 'send'),
        ):
            main.send_single_message(tg_api, vk_api, msg)
        called_text = tg_mock.call_args[0][0]['text']
        assert len(called_text) == 1500 + 3 + 1000  # 1500 + '...' + 1000
        assert called_text.startswith('A' * 1500)
        assert called_text.endswith('A' * 1000)

    def test_parses_disable_web_page_preview(self):
        """message_params with disable_web_page_preview='True' → converted to bool True."""
        msg = self._make_msg(
            messenger='telegram',
            message_params='{"disable_web_page_preview": "True"}',
        )
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        with (
            patch.object(TGApiBase, 'send_message', MagicMock(return_value='completed')) as tg_mock,
            patch.object(VKApi, 'send'),
        ):
            main.send_single_message(tg_api, vk_api, msg)
        params = tg_mock.call_args[0][0]
        assert params['disable_web_page_preview'] is True

    def test_parses_disable_web_page_preview_false(self):
        """message_params with disable_web_page_preview='False' → converted to bool False."""
        msg = self._make_msg(
            messenger='telegram',
            message_params='{"disable_web_page_preview": "False"}',
        )
        tg_api = TGApiBase(token='token')
        vk_api = VKApi('token')
        with (
            patch.object(TGApiBase, 'send_message', MagicMock(return_value='completed')) as tg_mock,
            patch.object(VKApi, 'send'),
        ):
            main.send_single_message(tg_api, vk_api, msg)
        params = tg_mock.call_args[0][0]
        assert params['disable_web_page_preview'] is False


# ─── Category 4: Integration tests ───


@pytest.mark.xdist_group(name='send_notifications')
class TestIntegration:
    """Integration tests for iterate_over_notifications with VK messenger."""

    def test_iterate_over_notifications_with_vk_messenger(self):
        """NotifByUser with messenger='vk' + user_identity_map → sent via VK API."""
        time_analytics = TimeAnalyticsFactory.build()
        user_id = randint(10_000_000, 99_999_999)
        vk_user_id = str(randint(100_000, 999_999))

        pool = sqlalchemy_get_pool()
        with pool.connect() as conn:
            _ensure_identity_map(conn, user_id, 'vk', vk_user_id)

        NotSentNotificationFactory.create_sync(
            user_id=user_id,
            messenger='vk',
            message_type='text',
        )

        with (
            patch.object(TGApiBase, '_process_response_of_api_call', MagicMock(return_value='completed')),
            patch.object(VKApi, 'send', MagicMock(return_value={})) as vk_mock,
        ):
            main.iterate_over_notifications(1, time_analytics)

        vk_mock.assert_called()
        # Verify at least one call was for our user
        vk_calls = vk_mock.call_args_list
        user_calls = [c for c in vk_calls if c[0][0] == vk_user_id]
        assert len(user_calls) >= 1

    def test_iterate_over_notifications_mixed_messengers(self):
        """Both VK and Telegram messages → each sent via correct channel."""
        time_analytics = TimeAnalyticsFactory.build()
        tg_user_id = randint(10_000_000, 99_999_999)
        vk_user_id = randint(10_000_000, 99_999_999)
        vk_uid_str = str(randint(100_000, 999_999))

        pool = sqlalchemy_get_pool()
        with pool.connect() as conn:
            _ensure_identity_map(conn, vk_user_id, 'vk', vk_uid_str)

        NotSentNotificationFactory.create_sync(
            user_id=tg_user_id,
            messenger='telegram',
            message_type='text',
        )
        NotSentNotificationFactory.create_sync(
            user_id=vk_user_id,
            messenger='vk',
            message_type='text',
        )

        tg_send = MagicMock(return_value='completed')
        vk_send = MagicMock(return_value={})

        with (
            patch.object(TGApiBase, '_process_response_of_api_call', tg_send),
            patch.object(VKApi, 'send', vk_send),
        ):
            main.iterate_over_notifications(1, time_analytics)

        # VK API should have been called for the VK-destined message
        vk_calls = vk_send.call_args_list
        vk_user_calls = [c for c in vk_calls if c[0][0] == vk_uid_str]
        assert len(vk_user_calls) >= 1

    def test_iterate_over_notifications_with_max_messenger(self):
        """NotifByUser with messenger='max' + user_identity_map → sent via MaxClient."""
        time_analytics = TimeAnalyticsFactory.build()
        user_id = randint(10_000_000, 99_999_999)
        max_user_id = str(randint(100_000, 999_999))

        pool = sqlalchemy_get_pool()
        with pool.connect() as conn:
            _ensure_identity_map(conn, user_id, 'max', max_user_id)

        NotSentNotificationFactory.create_sync(
            user_id=user_id,
            messenger='max',
            message_type='text',
        )

        max_client = MagicMock(spec=MaxClient)
        max_client.send_message.return_value = SendResult(success=True, status='completed')

        with (
            patch.object(TGApiBase, '_process_response_of_api_call', MagicMock(return_value='completed')),
            patch.object(VKApi, 'send', MagicMock(return_value={})),
            patch('send_notifications.main.get_default_max_client', return_value=max_client),
        ):
            main.iterate_over_notifications(1, time_analytics)

        max_client.send_message.assert_called()
        # Verify at least one call was for our user
        max_calls = max_client.send_message.call_args_list
        user_calls = [c for c in max_calls if c[0][0].messenger_user_id == max_user_id]
        assert len(user_calls) >= 1


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
    tg_api = TGApiBase(token='token')
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
        message_html = 'НЖ – изменение статуса по <a href="https://lizaalert.org/forum/viewtopic.php?t=123">Иванова ж40 лет</a> (Москва и МО – Активные поиски)'

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
                'Комментарии от <a href="https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u=107175">Странник_klg</a>:',
                'Комментарии от Странник_klg:',
                # remove whole links starting with https://lizaalert.org/forum/memberlist.php
            ),
            (
                '«<a href="https://lizaalert.org/forum/viewtopic.php?&t=367030&start=36">Странник_klg, в экипаже с Амрита, РВП позже   </a>',
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
