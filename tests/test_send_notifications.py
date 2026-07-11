"""Tests for send_notifications — fakes for NotificationSender, real-DB for DBClient."""

import datetime
from random import randint
from typing import Any

import pytest
import sqlalchemy
from polyfactory.factories import DataclassFactory
from sqlalchemy.engine import Connection

from _dependencies.common.commons import sqlalchemy_get_pool
from send_notifications._utils.clients.max_notificator import MaxNotificator
from send_notifications._utils.clients.telegram_notificator import TelegramNotificator
from send_notifications._utils.clients.vk_notificator import VKNotificator
from send_notifications._utils.database import DBClient, MessageToSend
from send_notifications._utils.helpers import (
    _prepare_message,
    format_mesage_for_vk,
    seconds_between,
    seconds_between_round_2,
    time_is_out,
)
from send_notifications._utils.models import TimeAnalytics
from send_notifications._utils.services.notification_sender import NotificationSender
from tests.common import find_model
from tests.factories.db_factories import NotifByUserFactory, UserFactory, get_session
from tests.factories.db_models import NotifByUser

# ─── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(scope='session')
def db_client():
    yield DBClient()


# ─── Helper factory / message builder ──────────────────────────────


class TimeAnalyticsFactory(DataclassFactory[TimeAnalytics]):
    script_start_time = datetime.datetime.now()


class NotSentNotificationFactory(NotifByUserFactory):
    completed = None
    cancelled = None
    failed = None
    created = datetime.datetime.now
    message_type = 'text'


def _make_msg(**kwargs: Any) -> MessageToSend:
    """Build a MessageToSend with sensible defaults."""
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
    return MessageToSend(**defaults)  # type: ignore[arg-type]


# ─── Fake notificators ─────────────────────────────────────────────


class FakeVKNotificator(VKNotificator):
    """Fake VK notificator that records calls instead of sending."""

    def __init__(self) -> None:
        # Skip VKNotificator.__init__ — no real VKApi needed
        self.sent_messages: list[tuple] = []

    def send_text(self, recipient: str | int, message_to_send: MessageToSend, content: str) -> str | None:
        self.sent_messages.append(('text', recipient, message_to_send, content))
        return 'completed'

    def send_coords(
        self,
        recipient: str | int,
        message_to_send: MessageToSend,
        latitude: float,
        longitude: float,
    ) -> str | None:
        self.sent_messages.append(('coords', recipient, message_to_send, latitude, longitude))
        return 'completed'

    def dispatch(
        self,
        message_to_send: MessageToSend,
        content: str,
        message_params: dict[str, Any],
    ) -> str | None:
        recipient = message_to_send.vk_id or message_to_send.user_id
        if message_to_send.message_type == 'text':
            return self.send_text(recipient, message_to_send, content)
        elif message_to_send.message_type == 'coords':
            return self.send_coords(recipient, message_to_send, message_params['latitude'], message_params['longitude'])
        else:
            raise ValueError(f'unknown message_type for VK: {message_to_send.message_type}')


class FakeTelegramNotificator(TelegramNotificator):
    """Fake Telegram notificator that records calls instead of sending."""

    def __init__(self) -> None:
        # Skip TelegramNotificator.__init__ — no real TGApiBase needed
        self.sent_messages: list[tuple] = []

    def send_text(self, user_id: int, content: str, message_params: dict[str, Any]) -> str | None:
        self.sent_messages.append(('text', user_id, content, message_params))
        return 'completed'

    def send_location(self, user_id: int, latitude: float, longitude: float) -> str | None:
        self.sent_messages.append(('coords', user_id, latitude, longitude))
        return 'completed'

    def dispatch(
        self,
        message_to_send: MessageToSend,
        content: str,
        message_params: dict[str, Any],
    ) -> str | None:
        if message_to_send.message_type == 'text':
            return self.send_text(message_to_send.user_id, content, message_params)
        elif message_to_send.message_type == 'coords':
            return self.send_location(message_to_send.user_id, message_params['latitude'], message_params['longitude'])
        else:
            raise ValueError(f'unknown message_type: {message_to_send.message_type}')


class FakeMaxNotificator(MaxNotificator):
    """Fake MAX notificator that records calls instead of sending."""

    def __init__(self) -> None:
        # Skip MaxNotificator.__init__ — no real MaxClient needed
        self.sent_messages: list[tuple] = []

    def send_text(self, message_to_send: MessageToSend, content: str) -> str | None:
        recipient = message_to_send.max_id or str(message_to_send.user_id)
        self.sent_messages.append(('text', recipient, message_to_send, content))
        return 'completed'

    def send_coords(self, message_to_send: MessageToSend, latitude: float, longitude: float) -> str | None:
        recipient = message_to_send.max_id or str(message_to_send.user_id)
        self.sent_messages.append(('coords', recipient, message_to_send, latitude, longitude))
        return 'completed'

    def dispatch(
        self,
        message_to_send: MessageToSend,
        content: str,
        message_params: dict[str, Any],
    ) -> str | None:
        if message_to_send.message_type == 'text':
            return self.send_text(message_to_send, content)
        elif message_to_send.message_type == 'coords':
            return self.send_coords(message_to_send, message_params['latitude'], message_params['longitude'])
        else:
            raise ValueError(f'unknown message_type for MAX: {message_to_send.message_type}')


class FakeDBClient(DBClient):
    """Fake DB client that stores data in-memory instead of hitting a real DB."""

    def __init__(self) -> None:
        # Skip DBClient.__init__ — no real engine needed
        self.notifications: list[MessageToSend] = []
        self.saved_statuses: dict[int, str | None] = {}
        self.change_log_times: dict[int, datetime.datetime | None] = {}
        self.recheck_doubling: bool = False
        self.saved_analytics: list[tuple] = []

    def get_notifs_to_send(self, select_doubling: bool = False) -> list[MessageToSend]:
        # Return only outstanding notifications (completed/cancelled/failed still None)
        if select_doubling and self.recheck_doubling:
            # Return copy for doubling detection logic
            return list(self.notifications)
        result = [n for n in self.notifications if n.completed is None and n.cancelled is None and n.failed is None]
        if select_doubling:
            return list(result)
        return result

    def save_sending_status_to_notif_by_user(self, message_id: int, result: str | None) -> None:
        self.saved_statuses[message_id] = result
        # Update message status so get_notifs_to_send() filters it out
        for msg in self.notifications:
            if msg.message_id == message_id:
                if result == 'completed':
                    msg.completed = datetime.datetime.now()
                elif result and result.startswith('cancelled'):
                    msg.cancelled = datetime.datetime.now()
                elif result == 'failed':
                    msg.failed = datetime.datetime.now()
                break

    def get_change_log_update_time(self, change_log_id: int) -> datetime.datetime | None:
        return self.change_log_times.get(change_log_id, None)

    def fill_vk_user_ids(self, messages: list[Any]) -> None:
        pass  # Assume vk_id is already set on test messages

    def fill_max_user_ids(self, messages: list[Any]) -> None:
        pass  # Assume max_id is already set on test messages

    def save_sending_analytics(self, num_msgs: int, speed: float, ttl_time: float) -> None:
        self.saved_analytics.append((num_msgs, speed, ttl_time))


@pytest.fixture
def fake_vk() -> FakeVKNotificator:
    return FakeVKNotificator()


@pytest.fixture
def fake_tg() -> FakeTelegramNotificator:
    return FakeTelegramNotificator()


@pytest.fixture
def fake_max() -> FakeMaxNotificator:
    return FakeMaxNotificator()


@pytest.fixture
def fake_db() -> FakeDBClient:
    return FakeDBClient()


@pytest.fixture
def sender(
    fake_vk: FakeVKNotificator, fake_tg: FakeTelegramNotificator, fake_max: FakeMaxNotificator, fake_db: FakeDBClient
) -> NotificationSender:
    return NotificationSender(
        db_client=fake_db,
        vk_notificator=fake_vk,
        tg_notificator=fake_tg,
        max_notificator=fake_max,
    )


# ─── DBClient integration tests (real DB) ──────────────────────────

# These use the real database through DBClient and are NOT replaced by fakes.


class TestDBClient:
    def test_get_change_log_update_time(self, db_client: DBClient):
        db_client.get_change_log_update_time(1)

    def test_save_sending_status_to_notif_by_user(self, db_client: DBClient):
        db_client.save_sending_status_to_notif_by_user(1, 'cancelled')

    def test_check_for_number_of_notifs_to_send(self, db_client: DBClient):
        NotSentNotificationFactory.create_batch_sync(3)
        result = db_client.check_for_number_of_notifs_to_send()
        assert result >= 3  # Could be more if other tests created notifications

    def test_save_sending_status_updates_correct_status(self, db_client: DBClient):
        notification = NotSentNotificationFactory.create_sync()
        db_client.save_sending_status_to_notif_by_user(notification.message_id, 'completed')

        updated = find_model(get_session(), NotifByUser, message_id=notification.message_id)
        assert updated.completed is not None
        assert updated.cancelled is None
        assert updated.failed is None

    def test_get_change_log_update_time_returns_none_for_invalid_id(self, db_client: DBClient):
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
        with pool.begin() as conn:
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

    def test_messenger_defaults_to_telegram(self, db_client: DBClient):
        """NotifByUser with messenger='telegram' → MessageToSend.messenger == 'telegram'."""
        msg_id = self._insert_notification(messenger='telegram')
        messages = db_client.get_notifs_to_send(select_doubling=False)
        match = [m for m in messages if m.message_id == msg_id]
        assert len(match) == 1
        assert match[0].messenger == 'telegram'

    def test_messenger_vk(self, db_client: DBClient):
        """NotifByUser with messenger='vk' → MessageToSend.messenger == 'vk'."""
        msg_id = self._insert_notification(messenger='vk')
        messages = db_client.get_notifs_to_send(select_doubling=False)
        match = [m for m in messages if m.message_id == msg_id]
        assert len(match) == 1
        assert match[0].messenger == 'vk'

    def test_messenger_mixed(self, db_client: DBClient):
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

    def _make_vk_notification(self, user_id: int) -> MessageToSend:
        """Create a VK-destined MessageToSend (not persisted)."""
        return _make_msg(user_id=user_id, messenger='vk')

    def _make_telegram_notification(self, user_id: int) -> MessageToSend:
        """Create a Telegram-destined MessageToSend (not persisted)."""
        return _make_msg(user_id=user_id, messenger='telegram')

    def test_no_vk_messages(self, db_client: DBClient):
        """No VK messages → early return, vk_id stays None for all messages."""
        tg_msg = self._make_telegram_notification(user_id=12345)
        db_client.fill_vk_user_ids([tg_msg])
        assert tg_msg.vk_id is None

    def test_from_identity_map(self, db_client: DBClient):
        """VK message, user in user_identity_map → vk_id filled."""
        user_id = randint(10_000_000, 99_999_999)
        vk_user_id = str(randint(100_000, 999_999))
        pool = sqlalchemy_get_pool()
        with pool.begin() as conn:
            _ensure_identity_map(conn, user_id, 'vk', vk_user_id)

        msg = self._make_vk_notification(user_id=user_id)
        db_client.fill_vk_user_ids([msg])
        assert msg.vk_id == vk_user_id

    def test_not_found(self, db_client: DBClient):
        """VK message, user not in identity_map → vk_id stays None."""
        user_id = randint(10_000_000, 99_999_999)
        UserFactory.create_sync(user_id=user_id, internal_user_id=user_id, vk_id=None)

        msg = self._make_vk_notification(user_id=user_id)
        db_client.fill_vk_user_ids([msg])
        assert msg.vk_id is None

    def test_multiple_users_mixed(self, db_client: DBClient):
        """Multiple VK messages: some from identity_map, some not found."""
        user_a = randint(10_000_000, 99_999_999)
        user_b = randint(10_000_000, 99_999_999)
        vk_a = str(randint(100_000, 999_999))

        pool = sqlalchemy_get_pool()
        with pool.begin() as conn:
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

    def _make_max_notification(self, user_id: int) -> MessageToSend:
        return _make_msg(user_id=user_id, messenger='max')

    def _make_telegram_notification(self, user_id: int) -> MessageToSend:
        return _make_msg(user_id=user_id, messenger='telegram')

    def test_no_max_messages(self, db_client: DBClient):
        """No MAX messages → early return, max_id stays None for all messages."""
        tg_msg = self._make_telegram_notification(user_id=12345)
        db_client.fill_max_user_ids([tg_msg])
        assert tg_msg.max_id is None

    def test_from_identity_map(self, db_client: DBClient):
        """MAX message, user in user_identity_map → max_id filled."""
        user_id = randint(10_000_000, 99_999_999)
        max_user_id = str(randint(100_000, 999_999))
        pool = sqlalchemy_get_pool()
        with pool.begin() as conn:
            _ensure_identity_map(conn, user_id, 'max', max_user_id)

        msg = self._make_max_notification(user_id=user_id)
        db_client.fill_max_user_ids([msg])
        assert msg.max_id == max_user_id

    def test_not_found(self, db_client: DBClient):
        """MAX message, user not in identity_map → max_id stays None."""
        user_id = randint(10_000_000, 99_999_999)
        msg = self._make_max_notification(user_id=user_id)
        db_client.fill_max_user_ids([msg])
        assert msg.max_id is None

    def test_multiple_users_mixed(self, db_client: DBClient):
        """Multiple MAX messages: some from identity_map, some not found."""
        user_a = randint(10_000_000, 99_999_999)
        user_b = randint(10_000_000, 99_999_999)
        max_a = str(randint(100_000, 999_999))

        pool = sqlalchemy_get_pool()
        with pool.begin() as conn:
            _ensure_identity_map(conn, user_a, 'max', max_a)

        msgs = [
            self._make_max_notification(user_id=user_a),
            self._make_max_notification(user_id=user_b),
        ]
        db_client.fill_max_user_ids(msgs)
        assert msgs[0].max_id == max_a
        assert msgs[1].max_id is None


# ─── Category 3: helpers tests (pure functions) ────────────────────


class TestHelpers:
    """Tests for pure helper functions."""

    def test_seconds_between(self):
        now = datetime.datetime.now()
        later = now + datetime.timedelta(seconds=5)
        assert seconds_between(now, later) == 5.0
        assert seconds_between(later, now) == 5.0

    def test_seconds_between_none_default(self):
        now = datetime.datetime.now()
        result = seconds_between(now - datetime.timedelta(seconds=3))
        assert result == pytest.approx(3.0, abs=0.1)

    def test_seconds_between_round_2(self):
        now = datetime.datetime.now()
        later = now + datetime.timedelta(seconds=5.123)
        assert seconds_between_round_2(now, later) == 5.12

    def test_time_is_out_false(self):
        start = datetime.datetime.now()
        assert not time_is_out(start)

    def test_prepare_message_truncates_long_text(self):
        long_text = 'A' * 4000
        msg = _make_msg(message_content=long_text)
        content, _ = _prepare_message(msg)
        assert len(content) == 1500 + 3 + 1000  # 1500 + '...' + 1000
        assert content.startswith('A' * 1500)
        assert content.endswith('A' * 1000)

    def test_prepare_message_parses_disable_web_page_preview(self):
        msg = _make_msg(message_params='{"disable_web_page_preview": "True"}')
        _, params = _prepare_message(msg)
        assert params['disable_web_page_preview'] is True

    def test_prepare_message_parses_disable_web_page_preview_false(self):
        msg = _make_msg(message_params='{"disable_web_page_preview": "False"}')
        _, params = _prepare_message(msg)
        assert params['disable_web_page_preview'] is False


# ─── Category 4: VKNotificator unit tests ─────────────────────────


class TestVKNotificator:
    """Tests for VKNotificator with fakes."""

    def test_send_text_ok(self):
        msg = _make_msg()
        vk = FakeVKNotificator()
        result = vk.send_text('12345', msg, 'hello')
        assert result == 'completed'
        assert len(vk.sent_messages) == 1
        kind, recipient, _, content = vk.sent_messages[0]
        assert kind == 'text'
        assert recipient == '12345'
        assert content == 'hello'

    def test_dispatch_text(self):
        msg = _make_msg(messenger='vk', vk_id='999', message_type='text', message_content='hello vk')
        vk = FakeVKNotificator()
        result = vk.dispatch(msg, 'hello vk', {})
        assert result == 'completed'
        assert len(vk.sent_messages) == 1
        _, recipient, _, content = vk.sent_messages[0]
        assert recipient == '999'  # uses vk_id
        assert content == 'hello vk'

    def test_dispatch_coords(self):
        msg = _make_msg(messenger='vk', vk_id='999', message_type='coords')
        vk = FakeVKNotificator()
        result = vk.dispatch(msg, '', {'latitude': 55.75, 'longitude': 37.62})
        assert result == 'completed'
        _, _, _, lat, long = vk.sent_messages[0]
        assert lat == 55.75
        assert long == 37.62

    def test_dispatch_unknown_type_raises(self):
        msg = _make_msg(messenger='vk', message_type='unknown')
        vk = FakeVKNotificator()
        with pytest.raises(ValueError, match='unknown message_type for VK'):
            vk.dispatch(msg, '', {})


# ─── Category 5: TelegramNotificator unit tests ────────────────────


class TestTelegramNotificator:
    """Tests for TelegramNotificator with fakes."""

    def test_send_text_ok(self):
        tg = FakeTelegramNotificator()
        result = tg.send_text(12345, 'hello', {'parse_mode': 'HTML'})
        assert result == 'completed'
        assert len(tg.sent_messages) == 1
        _, user_id, content, params = tg.sent_messages[0]
        assert user_id == 12345
        assert content == 'hello'
        assert params['parse_mode'] == 'HTML'

    def test_send_location_ok(self):
        tg = FakeTelegramNotificator()
        result = tg.send_location(12345, 55.75, 37.62)
        assert result == 'completed'
        assert len(tg.sent_messages) == 1
        _, user_id, lat, long = tg.sent_messages[0]
        assert user_id == 12345
        assert lat == 55.75
        assert long == 37.62

    def test_dispatch_text(self):
        msg = _make_msg(messenger='telegram', message_type='text', message_content='hello tg')
        tg = FakeTelegramNotificator()
        result = tg.dispatch(msg, 'hello tg', {'parse_mode': 'HTML'})
        assert result == 'completed'
        assert len(tg.sent_messages) == 1
        _, user_id, content, params = tg.sent_messages[0]
        assert user_id == msg.user_id
        assert content == 'hello tg'

    def test_dispatch_coords(self):
        msg = _make_msg(messenger='telegram', message_type='coords')
        tg = FakeTelegramNotificator()
        result = tg.dispatch(msg, '', {'latitude': 55.75, 'longitude': 37.62})
        assert result == 'completed'
        _, user_id, lat, long = tg.sent_messages[0]
        assert user_id == msg.user_id
        assert lat == 55.75
        assert long == 37.62


# ─── Category 6: MaxNotificator unit tests ─────────────────────────


class TestMaxNotificator:
    """Tests for MaxNotificator with fakes."""

    def test_send_text_ok(self):
        msg = _make_msg(max_id='54321')
        mx = FakeMaxNotificator()
        result = mx.send_text(msg, 'hello max')
        assert result == 'completed'
        assert len(mx.sent_messages) == 1
        _, recipient, _, content = mx.sent_messages[0]
        assert recipient == '54321'
        assert content == 'hello max'

    def test_dispatch_text(self):
        msg = _make_msg(messenger='max', max_id='54321', message_type='text', message_content='hello max')
        mx = FakeMaxNotificator()
        result = mx.dispatch(msg, 'hello max', {})
        assert result == 'completed'
        _, recipient, _, content = mx.sent_messages[0]
        assert recipient == '54321'

    def test_dispatch_coords(self):
        msg = _make_msg(messenger='max', max_id='54321', message_type='coords')
        mx = FakeMaxNotificator()
        result = mx.dispatch(msg, '', {'latitude': 55.75, 'longitude': 37.62})
        assert result == 'completed'
        _, recipient, _, lat, long = mx.sent_messages[0]
        assert recipient == '54321'
        assert lat == 55.75
        assert long == 37.62


# ─── Category 7: NotificationSender._send_one() tests ──────────────


class TestSendOne:
    """Tests for NotificationSender._send_one() — dispatch by messenger."""

    def test_vk_text(self, sender: NotificationSender, fake_vk: FakeVKNotificator):
        """messenger='vk', message_type='text' → VKNotificator called."""
        msg = _make_msg(messenger='vk', message_type='text', message_content='hello vk')
        result = sender._send_one(msg)
        assert result == 'completed'
        assert len(fake_vk.sent_messages) == 1
        _, recipient, _, content = fake_vk.sent_messages[0]
        assert recipient == msg.user_id
        assert 'hello vk' in content

    def test_vk_text_with_vk_id(self, sender: NotificationSender, fake_vk: FakeVKNotificator):
        """messenger='vk', vk_id set → uses vk_id as recipient."""
        msg = _make_msg(messenger='vk', message_type='text', vk_id='98765')
        sender._send_one(msg)
        assert len(fake_vk.sent_messages) == 1
        _, recipient, _, _ = fake_vk.sent_messages[0]
        assert recipient == '98765'

    def test_vk_coords(self, sender: NotificationSender, fake_vk: FakeVKNotificator):
        """messenger='vk', message_type='coords' → VKNotificator.send_coords called."""
        msg = _make_msg(
            messenger='vk',
            message_type='coords',
            message_params='{"latitude": 55.75, "longitude": 37.62}',
        )
        sender._send_one(msg)
        assert len(fake_vk.sent_messages) == 1
        kind, _, _, lat, long = fake_vk.sent_messages[0]
        assert kind == 'coords'
        assert lat == 55.75
        assert long == 37.62

    def test_telegram_text(self, sender: NotificationSender, fake_tg: FakeTelegramNotificator):
        """messenger='telegram', message_type='text' → TelegramNotificator called."""
        msg = _make_msg(messenger='telegram', message_type='text', message_content='hello tg')
        sender._send_one(msg)
        assert len(fake_tg.sent_messages) == 1
        _, user_id, content, _ = fake_tg.sent_messages[0]
        assert user_id == msg.user_id
        assert content == 'hello tg'

    def test_telegram_coords(self, sender: NotificationSender, fake_tg: FakeTelegramNotificator):
        """messenger='telegram', message_type='coords' → TelegramNotificator.send_location called."""
        msg = _make_msg(
            messenger='telegram',
            message_type='coords',
            message_params='{"latitude": 55.75, "longitude": 37.62}',
        )
        sender._send_one(msg)
        assert len(fake_tg.sent_messages) == 1
        kind, user_id, lat, long = fake_tg.sent_messages[0]
        assert kind == 'coords'
        assert user_id == msg.user_id
        assert lat == 55.75
        assert long == 37.62

    def test_max_text(self, sender: NotificationSender, fake_max: FakeMaxNotificator):
        """messenger='max', message_type='text' → MaxNotificator called."""
        msg = _make_msg(messenger='max', message_type='text', message_content='hello max', max_id='54321')
        sender._send_one(msg)
        assert len(fake_max.sent_messages) == 1
        _, recipient, _, content = fake_max.sent_messages[0]
        assert recipient == '54321'
        assert content == 'hello max'

    def test_max_coords(self, sender: NotificationSender, fake_max: FakeMaxNotificator):
        """messenger='max', message_type='coords' → MaxNotificator.send_coords called."""
        msg = _make_msg(
            messenger='max',
            message_type='coords',
            message_params='{"latitude": 55.75, "longitude": 37.62}',
            max_id='54321',
        )
        sender._send_one(msg)
        assert len(fake_max.sent_messages) == 1
        kind, recipient, _, lat, long = fake_max.sent_messages[0]
        assert kind == 'coords'
        assert recipient == '54321'

    def test_truncates_long_text(self, sender: NotificationSender, fake_tg: FakeTelegramNotificator):
        """message_content > 3000 chars → truncated to 1500 + ... + 1000."""
        long_text = 'A' * 4000
        msg = _make_msg(messenger='telegram', message_content=long_text)
        sender._send_one(msg)
        assert len(fake_tg.sent_messages) == 1
        _, _, content, _ = fake_tg.sent_messages[0]
        assert len(content) == 1500 + 3 + 1000  # 1500 + '...' + 1000
        assert content.startswith('A' * 1500)
        assert content.endswith('A' * 1000)

    def test_parses_disable_web_page_preview(self, sender: NotificationSender, fake_tg: FakeTelegramNotificator):
        """message_params with disable_web_page_preview='True' → converted to bool True."""
        msg = _make_msg(messenger='telegram', message_params='{"disable_web_page_preview": "True"}')
        sender._send_one(msg)
        assert len(fake_tg.sent_messages) == 1
        _, _, _, params = fake_tg.sent_messages[0]
        assert params['disable_web_page_preview'] is True

    def test_parses_disable_web_page_preview_false(self, sender: NotificationSender, fake_tg: FakeTelegramNotificator):
        msg = _make_msg(messenger='telegram', message_params='{"disable_web_page_preview": "False"}')
        sender._send_one(msg)
        assert len(fake_tg.sent_messages) == 1
        _, _, _, params = fake_tg.sent_messages[0]
        assert params['disable_web_page_preview'] is False


# ─── Category 8: NotificationSender._process_message_sending tests ─


class TestProcessMessageSending:
    """Tests for NotificationSender._process_message_sending()."""

    def test_completed_saves_status(
        self,
        sender: NotificationSender,
        fake_db: FakeDBClient,
        fake_tg: FakeTelegramNotificator,
    ):
        """Completed send → status saved, change id added, analytics recorded."""
        msg = _make_msg(messenger='telegram', message_type='text')
        fake_db.notifications = [msg]
        time_analytics = TimeAnalytics(script_start_time=datetime.datetime.now())
        change_ids: set[int] = set()

        sender._process_message_sending(time_analytics, change_ids, msg)

        assert fake_db.saved_statuses[msg.message_id] == 'completed'
        assert msg.change_log_id in change_ids
        assert len(time_analytics.notif_times) == 1

    def test_failed_saves_status(
        self,
        sender: NotificationSender,
        fake_db: FakeDBClient,
        fake_vk: FakeVKNotificator,
    ):
        """Failed send → status saved, change id NOT added."""
        msg = _make_msg(messenger='vk', message_type='text')
        fake_db.notifications = [msg]

        # Make VK notificator return 'failed'
        fake_vk.send_text = lambda r, m, c: 'failed'  # type: ignore[assignment]

        time_analytics = TimeAnalytics(script_start_time=datetime.datetime.now())
        change_ids: set[int] = set()

        sender._process_message_sending(time_analytics, change_ids, msg)

        assert fake_db.saved_statuses[msg.message_id] == 'failed'
        assert msg.change_log_id not in change_ids

    def test_updates_analytics_on_completed(
        self,
        sender: NotificationSender,
        fake_db: FakeDBClient,
        fake_tg: FakeTelegramNotificator,
    ):
        """Completed send → delays and parsed_times recorded."""
        msg = _make_msg(messenger='telegram', message_type='text')
        fake_db.notifications = [msg]
        fake_db.change_log_times[msg.change_log_id] = datetime.datetime.now()

        time_analytics = TimeAnalytics(script_start_time=datetime.datetime.now())
        change_ids: set[int] = set()

        sender._process_message_sending(time_analytics, change_ids, msg)

        assert len(time_analytics.delays) == 1
        assert len(time_analytics.parsed_times) == 1


# ─── Category 9: NotificationSender.send_all() tests ───────────────


class TestSendAll:
    """Tests for NotificationSender.send_all()."""

    def test_sends_all_notifications(
        self,
        sender: NotificationSender,
        fake_db: FakeDBClient,
        fake_tg: FakeTelegramNotificator,
    ):
        """Multiple notifications → all sent."""
        msgs = [
            _make_msg(
                messenger='telegram', message_type='text', message_id=1, change_log_id=10, message_content='msg1'
            ),
            _make_msg(
                messenger='telegram', message_type='text', message_id=2, change_log_id=20, message_content='msg2'
            ),
        ]
        fake_db.notifications = list(msgs)

        time_analytics = TimeAnalytics(script_start_time=datetime.datetime.now())
        result = sender.send_all(1, time_analytics)

        assert len(fake_tg.sent_messages) == 2
        assert sorted(result) == [10, 20]
        assert 1 in fake_db.saved_statuses
        assert 2 in fake_db.saved_statuses
        assert fake_db.saved_statuses[1] == 'completed'
        assert fake_db.saved_statuses[2] == 'completed'

    def test_sends_by_messenger(
        self,
        sender: NotificationSender,
        fake_db: FakeDBClient,
        fake_vk: FakeVKNotificator,
        fake_tg: FakeTelegramNotificator,
        fake_max: FakeMaxNotificator,
    ):
        """Messages with different messengers → each sent by correct notificator."""
        msgs = [
            _make_msg(messenger='telegram', message_type='text', message_id=1, vk_id=None),
            _make_msg(messenger='vk', message_type='text', message_id=2, vk_id='111'),
            _make_msg(messenger='max', message_type='text', message_id=3, max_id='222'),
        ]
        fake_db.notifications = list(msgs)

        time_analytics = TimeAnalytics(script_start_time=datetime.datetime.now())
        sender.send_all(1, time_analytics)

        assert len(fake_tg.sent_messages) == 1
        assert len(fake_vk.sent_messages) == 1
        assert len(fake_max.sent_messages) == 1

    def test_no_messages_then_new(
        self,
        sender: NotificationSender,
        fake_db: FakeDBClient,
        fake_tg: FakeTelegramNotificator,
    ):
        """Empty initial state → waits, gets new messages, sends them."""
        time_analytics = TimeAnalytics(script_start_time=datetime.datetime.now())

        # Use a thread to simulate delayed notifications
        import threading

        def add_notification():
            import time as _time

            _time.sleep(0.2)
            fake_db.notifications.append(_make_msg(messenger='telegram', message_type='text', message_id=99))

        t = threading.Thread(target=add_notification, daemon=True)
        t.start()

        # send_all will loop and eventually find the notification
        result = sender.send_all(1, time_analytics)

        assert len(fake_tg.sent_messages) >= 1
        assert len(result) >= 1


# ─── Category 10: _finish_analytics tests ──────────────────────────


class TestFinishAnalytics:
    """Tests for NotificationSender._finish_analytics()."""

    def test_with_data(self, sender: NotificationSender, fake_db: FakeDBClient):
        """Analytics with data → DB gets analytics, no crash."""
        time_analytics = TimeAnalytics(
            delays=[1],
            notif_times=[1, 2],
            parsed_times=[1, 2, 3],
            script_start_time=datetime.datetime.now(),
        )
        sender._finish_analytics(time_analytics, [1])
        assert len(fake_db.saved_analytics) == 1

    def test_without_data(self, sender: NotificationSender, fake_db: FakeDBClient):
        """Analytics without notif_times → no DB write, no crash."""
        time_analytics = TimeAnalytics(script_start_time=datetime.datetime.now())
        sender._finish_analytics(time_analytics, [])
        assert len(fake_db.saved_analytics) == 0


# ─── Category 11: format_mesage_for_vk tests (pure function) ───────


class TestFormatMessageForVK:
    @pytest.mark.parametrize(
        'input,result',
        [
            (
                'НЖ <a href="https://lizaalert.org/forum/viewtopic.php?t=123">Иванова ж40 лет</a> (Самара)',
                'НЖ https://lizaalert.org/forum/viewtopic.php?t=123 Иванова ж40 лет (Самара)',
            ),
            (
                'Комментарии от <a href="https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u=107175">Странник_klg</a>:',
                'Комментарии от Странник_klg:',
            ),
            (
                '«<a href="https://lizaalert.org/forum/viewtopic.php?&t=367030&start=36">Странник_klg, в экипаже с Амрита, РВП позже   </a>',
                '«Странник_klg, в экипаже с Амрита, РВП позже   ',
            ),
            (
                '<i>some text and other links</i>',
                'some text and other links',
            ),
            (
                '<s>some text and other links</s>',
                'some text and other links',
            ),
            (
                '<b>some text and other links</b>',
                'some text and other links',
            ),
            (
                ' <a href="tel:+79001234567"> ☎️+79001234567</a>»',
                '  ☎️+79001234567»',
            ),
            (
                '<b> <a href="tel:+79001234567"> ☎️+79001234567</a>»</b>',
                '  ☎️+79001234567»',
            ),
        ],
    )
    def test_format(self, input: str, result: str):
        assert format_mesage_for_vk(input) == result


# ─── Helper for identity map ───────────────────────────────────────


def _ensure_identity_map(conn: Connection, internal_user_id: int, messenger: str, messenger_user_id: str) -> None:
    """Insert into user_identity_map with ON CONFLICT DO NOTHING."""
    conn.execute(
        sqlalchemy.text("""
            INSERT INTO user_identity_map (internal_user_id, messenger, messenger_user_id)
            VALUES (:internal_user_id, :messenger, :messenger_user_id)
            ON CONFLICT DO NOTHING
        """),
        {'internal_user_id': internal_user_id, 'messenger': messenger, 'messenger_user_id': messenger_user_id},
    )
