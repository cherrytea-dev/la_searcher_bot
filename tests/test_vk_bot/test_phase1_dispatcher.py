"""Tests for VK Bot dispatcher and database modules.

These tests cover:
- DBClient (user resolution, VK ID management)
- dispatch_event (confirmation, message_new, message_event, other events)
- handle_unknown fallback handler
- HANDLER_CHAIN configuration
- _validate_invite_hash (from account_linking)
- handle_inline_pagination (from region_select_handlers)
"""

import hashlib
import random as _random
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.orm.session import Session
from sqlalchemy.pool import Pool

from _dependencies.commons import AppConfig
from _dependencies.telegram_api_wrapper import make_invite_text_for_user
from tests.factories import db_factories
from vk_bot._utils.account_linking import _validate_invite_hash
from vk_bot._utils.common import VKMessage
from vk_bot._utils.database import DBClient, DialogState, db
from vk_bot._utils.event_dispatcher import (
    HANDLER_CHAIN,
    dispatch_event,
    handle_unknown,
)
from vk_bot._utils.handlers.region_select_handlers import handle_inline_pagination

# ═══════════════════════════════════════════════════════════════════════════════
# DBClient (with real DB)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDBClient:
    """DBClient with real PostgreSQL connection."""

    @pytest.fixture
    def db_client(self, connection_pool: Pool) -> DBClient:
        return DBClient(connection_pool)

    def test_get_user_by_vk_id_not_found(self, db_client: DBClient):
        """Returns None when vk_id doesn't exist."""
        result = db_client.get_user_by_vk_id(-999999)
        assert result is None

    def test_get_user_by_vk_id_found(self, db_client: DBClient, session: Session):
        """Returns user_id when vk_id exists."""

        test_vk_id = _random.randint(100000, 999999)
        user = db_factories.UserFactory.create_sync(vk_id=str(test_vk_id))
        result = db_client.get_user_by_vk_id(test_vk_id)
        assert result == user.user_id

    def test_set_user_vk_id(self, db_client: DBClient, session: Session, user_id: int):
        """set_user_vk_id updates the vk_id column and returns True."""
        result = db_client.set_user_vk_id(user_id, vk_id=99999)
        assert result is True
        session.commit()

        with db_client.connect() as conn:
            row = conn.execute(
                sa_text('SELECT vk_id FROM users WHERE user_id = :uid'),
                uid=user_id,
            ).fetchone()
        assert row[0] == '99999'

    def test_set_user_vk_id_not_found(self, db_client: DBClient):
        """set_user_vk_id returns False when user doesn't exist."""
        result = db_client.set_user_vk_id(telegram_user_id=-999999, vk_id=99999)
        assert result is False

    def test_is_user_registered_in_vk_true(self, db_client: DBClient, session: Session):
        test_vk_id = _random.randint(100000, 999999)
        user = db_factories.UserFactory.create_sync(vk_id=str(test_vk_id))
        assert db_client.is_user_registered_in_vk(test_vk_id) is True

    def test_is_user_registered_in_vk_false(self, db_client: DBClient):
        assert db_client.is_user_registered_in_vk(-999) is False

    def test_resolve_user_id_linked(self, db_client: DBClient, session: Session):
        """Linked VK user returns telegram user_id."""

        test_vk_id = _random.randint(100000, 999999)
        user = db_factories.UserFactory.create_sync(vk_id=str(test_vk_id))
        result = db_client.resolve_user_id(test_vk_id)
        assert result == user.user_id
        assert result > 0

    def test_resolve_user_id_not_linked(self, db_client: DBClient):
        """Unlinked VK user returns -vk_user_id."""
        vk_id = 55555
        result = db_client.resolve_user_id(vk_id)
        assert result == -vk_id
        assert result < 0

    def test_db_singleton(self):
        """db() returns the same instance."""

        d1 = db()
        d2 = db()
        assert d1 is d2


# ═══════════════════════════════════════════════════════════════════════════════
# dispatch_event — confirmation
# ═══════════════════════════════════════════════════════════════════════════════


class TestDispatcherConfirmation:
    """Confirmation handshake."""

    def test_confirmation_valid(self, mock_app_config: AppConfig):
        """Valid confirmation returns vk_confirmation_code."""
        result = dispatch_event({'type': 'confirmation', 'group_id': 237036024})
        assert result == 'test_code'

    def test_confirmation_invalid_group(self):
        """Invalid group_id returns 'ok'."""
        result = dispatch_event({'type': 'confirmation', 'group_id': 999})
        assert result == 'ok'

    def test_confirmation_missing_group(self):
        """Missing group_id returns 'ok'."""
        result = dispatch_event({'type': 'confirmation'})
        assert result == 'ok'


# ═══════════════════════════════════════════════════════════════════════════════
# dispatch_event — message_new
# ═══════════════════════════════════════════════════════════════════════════════


class TestDispatcherMessageNew:
    """message_new event routing."""

    def test_message_new_without_object(self):
        """Event without object returns 'ok'."""
        result = dispatch_event({'type': 'message_new'})
        assert result == 'ok'

    def test_message_new_without_message(self):
        """Event without message data returns 'ok'."""
        result = dispatch_event({'type': 'message_new', 'object': {}})
        assert result == 'ok'

    def test_message_new_unknown_user(self, mock_vk_sender: MagicMock | AsyncMock):
        """Unlinked user gets invite instructions.

        Uses random vk_user_id to avoid stale data collisions
        (DB is not cleaned between test runs).

        NOTE: dispatch_event now processes events in a background thread
        to return 'ok' immediately. We wait briefly for the thread to execute.
        """

        vk_user_id = _random.randint(1000000, 9999999)
        event = {
            'type': 'message_new',
            'object': {
                'message': {
                    'from_id': vk_user_id,
                    'peer_id': vk_user_id,
                    'text': 'hello',
                    'id': 1,
                }
            },
        }

        result = dispatch_event(event)
        assert result == 'ok'
        # Wait for background thread to execute

        time.sleep(0.3)
        # VK-only user is now auto-registered and goes through handler chain
        # Since the text is not /start, it falls through to handle_unknown
        mock_vk_sender.return_value.send_message.assert_called_once()
        call_args = mock_vk_sender.return_value.send_message.call_args
        text = call_args[1].get('text', '') if 'text' in call_args[1] else call_args[0][1]
        assert 'понимаю' in text  # handle_unknown message

    def test_message_new_existing_user(
        self, session: Session, mock_vk_sender: MagicMock | AsyncMock, mock_dispatcher_db: MagicMock | AsyncMock
    ):
        """Existing linked user gets handler chain processing."""
        user = db_factories.UserFactory.create_sync()

        vk_user_id = _random.randint(1000000, 9999999)

        event = {
            'type': 'message_new',
            'object': {
                'message': {
                    'from_id': vk_user_id,
                    'peer_id': vk_user_id,
                    'text': 'some command',
                    'id': 1,
                }
            },
        }

        # Simulate that this VK user is linked to the Telegram user
        mock_dispatcher_db().get_user_by_vk_id.return_value = user.user_id

        result = dispatch_event(event)
        assert result == 'ok'
        # Wait for background thread to execute

        time.sleep(0.1)
        # Should have gone through handler chain (handle_unknown)
        mock_vk_sender.return_value.send_message.assert_called_once()

    def test_message_new_with_state(
        self, session: Session, mock_vk_sender: MagicMock | AsyncMock, mock_dispatcher_db: MagicMock | AsyncMock
    ):
        """User with active state gets handler chain."""
        user = db_factories.UserFactory.create_sync()

        vk_user_id = _random.randint(1000000, 9999999)

        # Set a state for this user
        db().set_user_state(user.user_id, DialogState.radius_input)

        event = {
            'type': 'message_new',
            'object': {
                'message': {
                    'from_id': vk_user_id,
                    'peer_id': vk_user_id,
                    'text': '50',
                    'id': 1,
                }
            },
        }

        # Simulate that this VK user is linked to the Telegram user
        mock_dispatcher_db().get_user_by_vk_id.return_value = user.user_id

        result = dispatch_event(event)
        assert result == 'ok'

        # Cleanup
        db().clear_user_state(user.user_id)

    def test_message_new_with_valid_invite(self, session: Session, mock_vk_sender: MagicMock | AsyncMock):
        """Unlinked user with valid invite text gets linked and sees main menu.

        Creates a real Telegram user in DB, generates a valid invite hash,
        and verifies that set_user_vk_id is called and main menu is sent.
        """

        # Create a real Telegram user in DB
        user = db_factories.UserFactory.create_sync()
        telegram_user_id = user.user_id

        # Generate valid invite text
        invite_text = make_invite_text_for_user(telegram_user_id)

        vk_user_id = _random.randint(1000000, 9999999)
        event = {
            'type': 'message_new',
            'object': {
                'message': {
                    'from_id': vk_user_id,
                    'peer_id': vk_user_id,
                    'text': invite_text,
                    'id': 1,
                }
            },
        }

        result = dispatch_event(event)
        assert result == 'ok'
        # Wait for background thread to execute

        time.sleep(0.3)

        # Should have called send_message with success text and main menu keyboard
        mock_vk_sender.return_value.send_message.assert_called_once()
        call_kwargs = mock_vk_sender.return_value.send_message.call_args[1]
        assert 'keyboard' in call_kwargs  # Should have a keyboard (main menu)
        assert call_kwargs['text'] == 'Теперь вы можете изменять настройки бота здесь'

        # Verify the VK ID was linked in the database
        linked_user_id = db().get_user_by_vk_id(vk_user_id)
        assert linked_user_id == telegram_user_id

        # Cleanup: remove the vk_id link

        with db().connect() as conn:
            conn.execute(sa_text('UPDATE users SET vk_id = NULL WHERE user_id = :uid'), uid=telegram_user_id)

    def test_message_new_with_stale_invite(self, mock_vk_sender: MagicMock | AsyncMock):
        """Valid invite hash but Telegram user doesn't exist in DB gets error message.

        This covers the case where a user deleted the bot or was removed from DB
        after the invite was generated.
        """

        # Use a non-existent telegram_user_id — no UserFactory created
        telegram_user_id = _random.randint(10000000, 99999999)
        invite_text = make_invite_text_for_user(telegram_user_id)

        vk_user_id = _random.randint(1000000, 9999999)
        event = {
            'type': 'message_new',
            'object': {
                'message': {
                    'from_id': vk_user_id,
                    'peer_id': vk_user_id,
                    'text': invite_text,
                    'id': 1,
                }
            },
        }

        result = dispatch_event(event)
        assert result == 'ok'
        time.sleep(0.3)

        # Should have called send_message with error about deleted bot
        mock_vk_sender.return_value.send_message.assert_called_once()
        call_args = mock_vk_sender.return_value.send_message.call_args
        text = call_args[1].get('text', '') if 'text' in call_args[1] else call_args[0][1]
        assert 'удалили бота' in text or 'код приглашения' in text

        # Verify no VK ID was linked
        assert db().get_user_by_vk_id(vk_user_id) is None

    def test_message_new_with_invalid_invite(self, mock_vk_sender: MagicMock | AsyncMock):
        """Unlinked user with invalid invite hash gets error message."""

        vk_user_id = _random.randint(1000000, 9999999)
        # Invalid invite text
        invite_text = 'telegram_id: 12345 invite_hash: invalidhash123'

        event = {
            'type': 'message_new',
            'object': {
                'message': {
                    'from_id': vk_user_id,
                    'peer_id': vk_user_id,
                    'text': invite_text,
                    'id': 1,
                }
            },
        }

        result = dispatch_event(event)
        assert result == 'ok'
        # Wait for background thread to execute

        time.sleep(0.3)

        # Should have called send_message with error about invalid code
        mock_vk_sender.return_value.send_message.assert_called_once()
        call_args = mock_vk_sender.return_value.send_message.call_args
        text = call_args[1].get('text', '') if 'text' in call_args[1] else call_args[0][1]
        assert 'Неверный код' in text


# ═══════════════════════════════════════════════════════════════════════════════
# dispatch_event — message_event
# ═══════════════════════════════════════════════════════════════════════════════


class TestDispatcherMessageEvent:
    """message_event (callback) routing."""

    def test_message_event(self, mock_vk_sender: MagicMock | AsyncMock):
        """Callback event is acknowledged."""
        event = {
            'type': 'message_event',
            'object': {
                'user_id': 123,
                'peer_id': 456,
                'message_id': 789,
                'payload': '{"button":"test"}',
                'event_id': 'evt_001',
            },
        }

        result = dispatch_event(event)
        assert result == 'ok'
        mock_vk_sender.return_value.send_callback_answer.assert_called_once_with(
            event_id='evt_001', user_id=123, peer_id=456
        )

    def test_message_event_without_event_id(self, mock_vk_sender: MagicMock | AsyncMock):
        """Callback without event_id still returns ok."""
        event = {
            'type': 'message_event',
            'object': {
                'user_id': 123,
                'peer_id': 456,
            },
        }

        result = dispatch_event(event)
        assert result == 'ok'
        # handle_callback_event returns early if payload is empty (no event_id)
        mock_vk_sender.return_value.send_callback_answer.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# dispatch_event — other event types
# ═══════════════════════════════════════════════════════════════════════════════


class TestDispatcherOther:
    """Other event types."""

    def test_unknown_event_type(self):
        """Unknown event type returns 'ok'."""
        result = dispatch_event({'type': 'wall_post_new', 'object': {}})
        assert result == 'ok'

    def test_empty_event(self):
        """Empty event returns 'ok'."""
        result = dispatch_event({})
        assert result == 'ok'


# ═══════════════════════════════════════════════════════════════════════════════
# handle_unknown
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleUnknown:
    """handle_unknown fallback handler."""

    def test_handle_unknown_returns_result(self):
        msg = VKMessage(text='unknown', user_id=1, peer_id=1)
        result = handle_unknown(msg, None)
        assert result is not None
        assert 'не понимаю' in result.text
        assert result.keyboard is not None

    def test_handle_unknown_with_state(self):
        msg = VKMessage(text='unknown', user_id=1, peer_id=1)
        result = handle_unknown(msg, DialogState.radius_input)
        assert result is not None
        assert 'не понимаю' in result.text


# ═══════════════════════════════════════════════════════════════════════════════
# HANDLER_CHAIN
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandlerChain:
    """HANDLER_CHAIN configuration."""

    def test_handler_chain_has_unknown(self):
        """Handler chain contains handle_unknown as fallback."""

        assert handle_unknown in HANDLER_CHAIN
        assert len(HANDLER_CHAIN) >= 1

    def test_handler_chain_last_is_unknown(self):
        """The last handler in chain is handle_unknown."""

        assert HANDLER_CHAIN[-1] is handle_unknown


# ═══════════════════════════════════════════════════════════════════════════════
# _validate_invite_hash
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateInviteHash:
    """_validate_invite_hash — invite hash validation."""

    def test_valid_hash(self, mock_app_config: AppConfig):
        """Valid hash returns True."""

        telegram_user_id = 12345
        expected_hash = hashlib.sha256(f'{telegram_user_id}test_secret'.encode()).hexdigest()

        result = _validate_invite_hash(telegram_user_id, expected_hash)
        assert result is True

    def test_invalid_hash(self, mock_app_config: AppConfig):
        """Invalid hash returns False."""

        result = _validate_invite_hash(12345, 'invalid_hash_value')
        assert result is False

    def test_different_user_id(self, mock_app_config: AppConfig):
        """Hash for different user_id returns False."""

        hash_for_user_1 = hashlib.sha256(f'{11111}test_secret'.encode()).hexdigest()

        # Hash was generated for user 11111, but we're validating for user 22222
        result = _validate_invite_hash(22222, hash_for_user_1)
        assert result is False

    def test_different_secret(self, mock_app_config: AppConfig):
        """Hash with different secret returns False."""

        telegram_user_id = 12345
        # Hash generated with a different secret
        wrong_hash = hashlib.sha256(f'{telegram_user_id}wrong_secret'.encode()).hexdigest()

        result = _validate_invite_hash(telegram_user_id, wrong_hash)
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# _handle_inline_pagination
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleInlinePagination:
    """handle_inline_pagination — inline pagination callback handler."""

    def test_paginate_nav_edits_message(self, dispatcher_mocks: dict[str, MagicMock | AsyncMock]):
        """paginate_nav edits the message in-place with new page."""

        msg = VKMessage(
            text='',
            user_id=100,
            peer_id=200,
            message_id=300,
            conversation_message_id=400,
            event_id='evt_001',
        )
        payload = {'cmd': 'paginate_nav', 'district': 'Центральный', 'page': 1}

        mock_get_folders = dispatcher_mocks['folders']
        mock_get_selected = dispatcher_mocks['selected']
        fake_sender = dispatcher_mocks['sender']

        mock_get_folders.return_value = [(1, 'Московская область'), (2, 'Тверская область')]
        mock_get_selected.return_value = ['Московская область']

        handle_inline_pagination(msg, payload, sender=fake_sender)

        # Should acknowledge the event
        fake_sender.assert_callback_answered(1)
        assert fake_sender.last_callback is not None
        assert fake_sender.last_callback.event_id == 'evt_001'
        assert fake_sender.last_callback.user_id == 100
        assert fake_sender.last_callback.peer_id == 200
        # Should edit the message (has conversation_message_id)
        fake_sender.assert_edited(1)
        assert fake_sender.last_edited is not None
        assert fake_sender.last_edited.peer_id == 200
        assert 'Центральный' in fake_sender.last_edited.text
        assert fake_sender.last_edited.conversation_message_id == 400

    def test_paginate_nav_no_folders_shows_snackbar(self, dispatcher_mocks: dict[str, MagicMock | AsyncMock]):
        """paginate_nav with no folders shows snackbar and returns early."""

        msg = VKMessage(
            text='',
            user_id=100,
            peer_id=200,
            event_id='evt_001',
        )
        payload = {'cmd': 'paginate_nav', 'district': 'Неизвестный', 'page': 0}

        mock_get_folders = dispatcher_mocks['folders']
        fake_sender = dispatcher_mocks['sender']

        mock_get_folders.return_value = []  # No folders

        handle_inline_pagination(msg, payload, sender=fake_sender)

        # Should show snackbar with error message
        fake_sender.assert_callback_answered(1)
        assert fake_sender.last_callback is not None
        assert fake_sender.last_callback.event_data == {
            'type': 'show_snackbar',
            'text': 'В этом округе пока нет доступных регионов.',
        }
        # Should NOT edit or send any message
        fake_sender.assert_edited(0)
        assert len(fake_sender.sent_messages) == 0

    def test_paginate_toggle_shows_snackbar_and_refreshes(self, dispatcher_mocks: dict[str, MagicMock | AsyncMock]):
        """paginate_toggle shows snackbar and refreshes keyboard."""

        msg = VKMessage(
            text='',
            user_id=100,
            peer_id=200,
            conversation_message_id=400,
            event_id='evt_002',
        )
        payload = {'cmd': 'paginate_toggle', 'region': 'Московская область', 'district': 'Центральный', 'page': 0}

        mock_get_folders = dispatcher_mocks['folders']
        mock_get_selected = dispatcher_mocks['selected']
        fake_sender = dispatcher_mocks['sender']
        mock_keyboard = dispatcher_mocks['keyboard']

        mock_get_folders.return_value = [(1, 'Московская область'), (2, 'Тверская область')]
        mock_get_selected.return_value = ['Московская область']

        # We need to patch _toggle_region_inline separately since it's not in dispatcher_mocks
        with patch('vk_bot._utils.handlers.region_select_handlers._toggle_region_inline') as mock_toggle:
            mock_toggle.return_value = '✅ Московская область добавлена'

            handle_inline_pagination(msg, payload, sender=fake_sender)

        # Should show snackbar with toggle result
        fake_sender.assert_callback_answered(1)
        assert fake_sender.last_callback is not None
        assert fake_sender.last_callback.event_data == {
            'type': 'show_snackbar',
            'text': '✅ Московская область добавлена',
        }
        # Should refresh the keyboard via edit_message
        fake_sender.assert_edited(1)

    def test_paginate_toggle_no_region_returns_early(self, dispatcher_mocks: dict[str, MagicMock | AsyncMock]):
        """paginate_toggle without region returns early."""

        msg = VKMessage(text='', user_id=100, peer_id=200)
        payload = {'cmd': 'paginate_toggle', 'region': ''}

        fake_sender = dispatcher_mocks['sender']

        handle_inline_pagination(msg, payload, sender=fake_sender)

        # Should not call anything
        fake_sender.assert_no_calls()

    def test_paginate_back_returns_to_districts(self, dispatcher_mocks: dict[str, MagicMock | AsyncMock]):
        """paginate_back edits message with district selection."""

        msg = VKMessage(
            text='',
            user_id=100,
            peer_id=200,
            conversation_message_id=400,
            event_id='evt_003',
        )
        payload = {'cmd': 'paginate_back'}

        fake_sender = dispatcher_mocks['sender']
        mock_keyboard = dispatcher_mocks['keyboard']

        handle_inline_pagination(msg, payload, sender=fake_sender)

        # Should acknowledge the event
        fake_sender.assert_callback_answered(1)
        assert fake_sender.last_callback is not None
        assert fake_sender.last_callback.event_id == 'evt_003'
        assert fake_sender.last_callback.user_id == 100
        assert fake_sender.last_callback.peer_id == 200
        # Should edit message with district selection
        fake_sender.assert_edited(1)
        assert fake_sender.last_edited is not None
        assert fake_sender.last_edited.conversation_message_id == 400

    def test_paginate_finish_removes_keyboard_and_sends_new_message(
        self, dispatcher_mocks: dict[str, MagicMock | AsyncMock]
    ):
        """paginate_finish removes inline keyboard and sends new settings message."""

        msg = VKMessage(
            text='',
            user_id=100,
            peer_id=200,
            conversation_message_id=400,
            event_id='evt_004',
        )
        payload = {'cmd': 'paginate_finish'}

        fake_sender = dispatcher_mocks['sender']
        mock_keyboard = dispatcher_mocks['keyboard']

        handle_inline_pagination(msg, payload, sender=fake_sender)

        # Should acknowledge the event
        fake_sender.assert_callback_answered(1)
        assert fake_sender.last_callback is not None
        assert fake_sender.last_callback.event_id == 'evt_004'
        assert fake_sender.last_callback.user_id == 100
        assert fake_sender.last_callback.peer_id == 200
        # Should edit message to remove inline keyboard
        fake_sender.assert_edited(1)
        assert fake_sender.last_edited is not None
        assert fake_sender.last_edited.conversation_message_id == 400
        assert 'завершён' in fake_sender.last_edited.text
        # Should send a new message with settings menu
        fake_sender.assert_sent(1)
        assert fake_sender.last_sent is not None
        assert 'keyboard' in fake_sender.last_sent.keyboard or fake_sender.last_sent.keyboard is not None

    def test_paginate_nav_fallback_to_message_id(self, dispatcher_mocks: dict[str, MagicMock | AsyncMock]):
        """paginate_nav falls back to message_id when no conversation_message_id."""

        msg = VKMessage(
            text='',
            user_id=100,
            peer_id=200,
            message_id=300,  # Only message_id, no conversation_message_id
            event_id='evt_005',
        )
        payload = {'cmd': 'paginate_nav', 'district': 'Центральный', 'page': 0}

        mock_get_folders = dispatcher_mocks['folders']
        mock_get_selected = dispatcher_mocks['selected']
        fake_sender = dispatcher_mocks['sender']
        mock_keyboard = dispatcher_mocks['keyboard']

        mock_get_folders.return_value = [(1, 'Московская область')]
        mock_get_selected.return_value = []

        handle_inline_pagination(msg, payload, sender=fake_sender)

        # Should edit with message_id fallback
        fake_sender.assert_edited(1)
        assert fake_sender.last_edited is not None
        assert fake_sender.last_edited.message_id == 300
        assert fake_sender.last_edited.conversation_message_id is None

    def test_paginate_nav_no_message_ids_is_noop(self, dispatcher_mocks: dict[str, MagicMock | AsyncMock]):
        """paginate_nav with no message IDs does nothing (edit is not possible)."""

        msg = VKMessage(
            text='',
            user_id=100,
            peer_id=200,
            # No message_id or conversation_message_id
            event_id='evt_006',
        )
        payload = {'cmd': 'paginate_nav', 'district': 'Центральный', 'page': 0}

        mock_get_folders = dispatcher_mocks['folders']
        mock_get_selected = dispatcher_mocks['selected']
        fake_sender = dispatcher_mocks['sender']
        mock_keyboard = dispatcher_mocks['keyboard']

        mock_get_folders.return_value = [(1, 'Московская область')]
        mock_get_selected.return_value = []

        handle_inline_pagination(msg, payload, sender=fake_sender)

        # _edit_message is a no-op when neither ID is available
        fake_sender.assert_edited(0)
        assert len(fake_sender.sent_messages) == 0
