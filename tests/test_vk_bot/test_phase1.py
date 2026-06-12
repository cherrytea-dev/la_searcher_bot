"""Tests for Phase 1 VK Bot infrastructure modules.

These tests cover:
- Data models (VKMessage, VKHandlerResult)
- URL constants
- VKKeyboard builder (layouts + presets)
- VKApi client extensions (send, edit, delete, error handling)
- VKMessageSender (rate limiting, error handling)
- DBClient (user resolution, VK ID management)
- Dispatcher (event routing, handler chain)
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from _dependencies.services.state_machine import DialogState, clear_user_state, set_user_state
from tests.factories import db_factories
from vk_bot._utils.common import VKHandlerResult, VKMessage
from vk_bot._utils.dispatcher import HANDLER_CHAIN, dispatch_event, handle_unknown
from vk_bot._utils.keyboards import VKKeyboard
from vk_bot._utils.message_sending import VKMessageSender, vk_sender

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_vk_api():
    """Create a mock VKApi client for VKMessageSender tests.

    VKMessageSender now accepts an optional `api` parameter,
    so tests can inject a mock directly: VKMessageSender(api=mock_vk_api).
    """
    api = MagicMock()
    api.send.return_value = {'response': {'message_id': 42}}
    api.edit_message.return_value = {'response': {}}
    api.delete_message.return_value = {'response': {}}
    api.send_message_event_answer.return_value = {'response': {}}
    yield api


# ═══════════════════════════════════════════════════════════════════════════════
# 1. common.py — VKMessage, VKHandlerResult, URL constants
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKMessage:
    """VKMessage Pydantic model."""

    def test_create_minimal(self):
        msg = VKMessage(text='hello', user_id=123, peer_id=456)
        assert msg.text == 'hello'
        assert msg.user_id == 123
        assert msg.peer_id == 456
        assert msg.message_id is None
        assert msg.payload is None
        assert msg.event_id is None

    def test_create_full(self):
        msg = VKMessage(
            text='hello',
            user_id=123,
            peer_id=456,
            message_id=789,
            payload='{"button":"test"}',
            event_id='evt_001',
        )
        assert msg.message_id == 789
        assert msg.payload == '{"button":"test"}'
        assert msg.event_id == 'evt_001'

    def test_serialization(self):
        msg = VKMessage(text='hello', user_id=123, peer_id=456)
        data = msg.model_dump()
        assert data['text'] == 'hello'
        assert data['user_id'] == 123
        assert data['peer_id'] == 456

    def test_deserialization(self):
        data = {'text': 'hello', 'user_id': 123, 'peer_id': 456, 'message_id': 789}
        msg = VKMessage.model_validate(data)
        assert msg.text == 'hello'
        assert msg.message_id == 789


class TestVKHandlerResult:
    """VKHandlerResult dataclass."""

    def test_minimal(self):
        result = VKHandlerResult(text='hello')
        assert result.text == 'hello'
        assert result.keyboard is None
        assert result.new_state is None
        assert result.edit_message_id is None
        assert result.attachment is None

    def test_full(self):
        keyboard = {'one_time': False, 'inline': False, 'buttons': []}
        result = VKHandlerResult(
            text='hello',
            keyboard=keyboard,
            new_state=DialogState.radius_input,
            edit_message_id=42,
            attachment='photo123',
        )
        assert result.keyboard == keyboard
        assert result.new_state == DialogState.radius_input
        assert result.edit_message_id == 42
        assert result.attachment == 'photo123'

    def test_default_factory(self):
        r1 = VKHandlerResult(text='a')
        r2 = VKHandlerResult(text='b')
        assert r1.keyboard is None
        assert r2.keyboard is None


class TestURLConstants:
    """URL constants from common.py."""

    def test_search_url_prefix(self):
        from vk_bot._utils.common import SEARCH_URL_PREFIX

        assert SEARCH_URL_PREFIX == 'https://lizaalert.org/forum/viewtopic.php?t='

    def test_forum_folder_prefix(self):
        from vk_bot._utils.common import FORUM_FOLDER_PREFIX

        assert FORUM_FOLDER_PREFIX == 'https://lizaalert.org/forum/viewforum.php?f='

    def test_hotline_phone(self):
        from vk_bot._utils.common import LA_HOTLINE_PHONE

        assert LA_HOTLINE_PHONE == '8-800-700-54-52'

    def test_website(self):
        from vk_bot._utils.common import LA_WEBSITE

        assert LA_WEBSITE == 'https://lizaalert.org'


# ═══════════════════════════════════════════════════════════════════════════════
# 2. keyboards.py — VKKeyboard
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKKeyboardLayout:
    """VKKeyboard layout methods."""

    def test_one_column(self):
        result = VKKeyboard.one_column(['A', 'B', 'C'])
        assert result['one_time'] is False
        assert result['inline'] is False
        assert len(result['buttons']) == 3
        for i, btn in enumerate(result['buttons']):
            assert len(btn) == 1  # one button per row
            assert btn[0]['action']['type'] == 'text'
            assert btn[0]['action']['label'] == ['A', 'B', 'C'][i]
            assert btn[0]['color'] == 'secondary'

    def test_one_column_with_color(self):
        result = VKKeyboard.one_column(['X'], color='primary')
        assert result['buttons'][0][0]['color'] == 'primary'

    def test_two_columns_even(self):
        result = VKKeyboard.two_columns(['A', 'B', 'C', 'D'])
        assert len(result['buttons']) == 2  # 2 rows
        assert len(result['buttons'][0]) == 2  # 2 buttons in first row
        assert len(result['buttons'][1]) == 2  # 2 buttons in second row
        assert result['buttons'][0][0]['action']['label'] == 'A'
        assert result['buttons'][0][1]['action']['label'] == 'B'
        assert result['buttons'][1][0]['action']['label'] == 'C'
        assert result['buttons'][1][1]['action']['label'] == 'D'

    def test_two_columns_odd(self):
        result = VKKeyboard.two_columns(['A', 'B', 'C'])
        assert len(result['buttons']) == 2  # 2 rows
        assert len(result['buttons'][0]) == 2  # A, B
        assert len(result['buttons'][1]) == 1  # C alone

    def test_two_columns_single(self):
        result = VKKeyboard.two_columns(['A'])
        assert len(result['buttons']) == 1
        assert len(result['buttons'][0]) == 1

    def test_one_row(self):
        result = VKKeyboard.one_row(['A', 'B', 'C'])
        assert len(result['buttons']) == 1
        assert len(result['buttons'][0]) == 3

    def test_one_row_single(self):
        result = VKKeyboard.one_row(['A'])
        assert len(result['buttons'][0]) == 1

    def test_inline_url(self):
        result = VKKeyboard.inline_url([('Label', 'https://example.com')])
        assert result['inline'] is True
        assert result['buttons'][0][0]['action']['type'] == 'open_link'
        assert result['buttons'][0][0]['action']['label'] == 'Label'
        assert result['buttons'][0][0]['action']['link'] == 'https://example.com'

    def test_inline_url_multiple(self):
        buttons = [('A', 'http://a.com'), ('B', 'http://b.com')]
        result = VKKeyboard.inline_url(buttons)
        assert len(result['buttons']) == 2  # each in its own row
        assert result['buttons'][0][0]['action']['link'] == 'http://a.com'
        assert result['buttons'][1][0]['action']['link'] == 'http://b.com'

    def test_empty(self):
        result = VKKeyboard.empty()
        assert result['buttons'] == []
        assert result['one_time'] is False
        assert result['inline'] is False

    def test_text_button_payload(self):
        """_text_button generates payload from label if not provided."""
        btn = VKKeyboard._text_button('Test Button')
        payload = json.loads(btn['action']['payload'])
        assert payload == {'button': 'Test Button'}

    def test_text_button_custom_payload(self):
        btn = VKKeyboard._text_button('X', payload='custom_payload')
        assert btn['action']['payload'] == 'custom_payload'

    def test_location_button(self):
        btn = VKKeyboard._location_button()
        assert btn['action']['type'] == 'location'


class TestVKKeyboardPresets:
    """VKKeyboard preset menus."""

    def test_main_menu(self):
        result = VKKeyboard.main_menu()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert '🔥Карта Поисков 🔥' in labels
        assert 'посмотреть актуальные поиски' in labels
        assert 'настроить бот' in labels
        assert 'другие возможности' in labels
        assert result['buttons'][0][0]['color'] == 'primary'

    def test_settings_menu(self):
        result = VKKeyboard.settings_menu()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert 'настроить виды уведомлений' in labels
        assert 'настроить "домашние координаты"' in labels
        assert 'связать аккаунты бота и форума' in labels
        assert 'в начало' in labels

    def test_coords_menu(self):
        result = VKKeyboard.coords_menu()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert 'ввести "домашние координаты" вручную' in labels
        assert 'посмотреть сохраненные "домашние координаты"' in labels
        assert 'удалить "домашние координаты"' in labels

    def test_role_choice(self):
        result = VKKeyboard.role_choice()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert 'я состою в ЛизаАлерт' in labels
        assert 'я хочу помогать ЛизаАлерт' in labels
        assert 'я ищу человека' in labels
        assert 'у меня другая задача' in labels
        assert 'не хочу говорить' in labels
        assert result['buttons'][0][0]['color'] == 'primary'

    def test_yes_no(self):
        result = VKKeyboard.yes_no()
        assert len(result['buttons']) == 1  # two_columns → one row with 2 buttons
        assert len(result['buttons'][0]) == 2
        assert result['buttons'][0][0]['action']['label'] == 'да, это я'
        assert result['buttons'][0][1]['action']['label'] == 'нет, это не я'

    def test_back_to_start(self):
        result = VKKeyboard.back_to_start()
        assert result['buttons'][0][0]['action']['label'] == 'в начало'

    def test_other_menu(self):
        result = VKKeyboard.other_menu()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert 'посмотреть последние поиски' in labels
        assert 'написать разработчику бота' in labels
        assert 'ознакомиться с информацией для новичка' in labels
        assert 'посмотреть красивые фото с поисков' in labels

    def test_distance_settings(self):
        result = VKKeyboard.distance_settings()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert 'включить ограничение по расстоянию' in labels
        assert 'отключить ограничение по расстоянию' in labels
        assert 'изменить ограничение по расстоянию' in labels

    def test_notification_settings(self):
        result = VKKeyboard.notification_settings()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert 'включить: все уведомления' in labels
        assert 'включить: о новых поисках' in labels
        assert 'включить: об изменениях статусов' in labels
        assert 'отключить: о новых поисках' in labels
        assert 'отключить: об изменениях статусов' in labels
        assert 'настроить более гибко' in labels
        assert 'в начало' in labels

    def test_fed_districts(self):
        result = VKKeyboard.fed_districts()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert 'Центральный ФО' in labels
        assert 'Северо-Западный ФО' in labels
        assert 'Южный ФО' in labels
        assert 'Северо-Кавказский ФО' in labels
        assert 'Приволжский ФО' in labels
        assert 'Уральский ФО' in labels
        assert 'Сибирский ФО' in labels
        assert 'Дальневосточный ФО' in labels
        assert 'Прочие поиски по РФ' in labels

    def test_is_moscow(self):
        result = VKKeyboard.is_moscow()
        assert result['buttons'][0][0]['action']['label'] == 'да, Москва – мой регион'
        assert result['buttons'][0][1]['action']['label'] == 'нет, я из другого региона'

    def test_help_needed(self):
        result = VKKeyboard.help_needed()
        assert result['buttons'][0][0]['action']['label'] == 'да, помогите мне настроить бот'
        assert result['buttons'][0][1]['action']['label'] == 'нет, помощь не требуется'


# ═══════════════════════════════════════════════════════════════════════════════
# 3. vk_api_client.py — VKApi (mocked HTTP)
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKApiSend:
    """VKApi.send() with mocked HTTP."""

    def test_send_basic(self, mock_vk_http):
        """Basic send without optional params."""
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {'message_id': 123}}

        from _dependencies.vk_api_client import VKApi

        api = VKApi(token='test_token')
        result = api.send(user_id=456, random_id=789, message='hello')

        assert result['response']['message_id'] == 123
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['params']['peer_id'] == 456
        assert call_kwargs['params']['random_id'] == 789
        assert call_kwargs['params']['message'] == 'hello'

    def test_send_with_keyboard(self, mock_vk_http):
        """Send with keyboard serialized to JSON."""
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        from _dependencies.vk_api_client import VKApi

        api = VKApi(token='test_token')
        keyboard = {'one_time': False, 'buttons': []}
        api.send(user_id=1, random_id=1, message='test', keyboard=keyboard)

        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs['json']
        assert 'keyboard' in payload
        assert json.loads(payload['keyboard']) == keyboard

    def test_send_with_attachment(self, mock_vk_http):
        """Send with attachment."""
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        from _dependencies.vk_api_client import VKApi

        api = VKApi(token='test_token')
        api.send(user_id=1, random_id=1, message='test', attachment='photo123_456')

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['json']['attachment'] == 'photo123_456'

    def test_send_dont_parse_links(self, mock_vk_http):
        """Send with dont_parse_links flag."""
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        from _dependencies.vk_api_client import VKApi

        api = VKApi(token='test_token')
        api.send(user_id=1, random_id=1, message='https://example.com', dont_parse_links=True)

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['json']['dont_parse_links'] == 1

    def test_send_with_coords(self, mock_vk_http):
        """Send with lat/long."""
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        from _dependencies.vk_api_client import VKApi

        api = VKApi(token='test_token')
        api.send(user_id=1, random_id=1, message='loc', lat='55.0', long='37.0')

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['params']['lat'] == '55.0'
        assert call_kwargs['params']['long'] == '37.0'


class TestVKApiEditMessage:
    """VKApi.edit_message() with mocked HTTP."""

    def test_edit_basic(self, mock_vk_http):
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        from _dependencies.vk_api_client import VKApi

        api = VKApi(token='test_token')
        api.edit_message(peer_id=1, message_id=2, message='new text')

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['params']['peer_id'] == 1
        assert call_kwargs['params']['message_id'] == 2
        assert call_kwargs['params']['message'] == 'new text'

    def test_edit_with_keyboard(self, mock_vk_http):
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        from _dependencies.vk_api_client import VKApi

        api = VKApi(token='test_token')
        keyboard = {'buttons': []}
        api.edit_message(peer_id=1, message_id=2, message='text', keyboard=keyboard)

        call_kwargs = mock_post.call_args[1]
        assert 'keyboard' in call_kwargs['json']


class TestVKApiDeleteMessage:
    """VKApi.delete_message() with mocked HTTP."""

    def test_delete(self, mock_vk_http):
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        from _dependencies.vk_api_client import VKApi

        api = VKApi(token='test_token')
        api.delete_message(peer_id=1, message_ids=[2, 3])

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['params']['peer_id'] == 1
        assert call_kwargs['params']['message_ids'] == '2,3'
        assert call_kwargs['params']['delete_for_all'] == 1


class TestVKApiSendMessageEventAnswer:
    """VKApi.send_message_event_answer() with mocked HTTP."""

    def test_answer_basic(self, mock_vk_http):
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        from _dependencies.vk_api_client import VKApi

        api = VKApi(token='test_token')
        api.send_message_event_answer(event_id='evt1', user_id=1, peer_id=2)

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['params']['event_id'] == 'evt1'
        assert call_kwargs['params']['user_id'] == 1
        assert call_kwargs['params']['peer_id'] == 2

    def test_answer_with_event_data(self, mock_vk_http):
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        from _dependencies.vk_api_client import VKApi

        api = VKApi(token='test_token')
        event_data = {'type': 'show_snackbar', 'text': 'Done!'}
        api.send_message_event_answer(event_id='evt1', user_id=1, peer_id=2, event_data=event_data)

        call_kwargs = mock_post.call_args[1]
        assert 'event_data' in call_kwargs['json']
        assert json.loads(call_kwargs['json']['event_data']) == event_data


class TestVKApiErrorHandling:
    """_handle_vk_error with various error codes."""

    def test_no_error(self, caplog):
        from _dependencies.vk_api_client import _handle_vk_error

        _handle_vk_error({'response': {}})
        assert len(caplog.records) == 0

    def test_error_code_1(self, caplog):
        from _dependencies.vk_api_client import _handle_vk_error

        _handle_vk_error({'error': {'error_code': 1, 'error_msg': 'unknown'}})
        assert any('unknown error' in r.message for r in caplog.records)

    def test_error_code_100(self, caplog):
        from _dependencies.vk_api_client import _handle_vk_error

        _handle_vk_error({'error': {'error_code': 100, 'error_msg': 'param'}})
        assert any('param error' in r.message for r in caplog.records)

    def test_error_code_200(self, caplog):
        from _dependencies.vk_api_client import _handle_vk_error

        _handle_vk_error({'error': {'error_code': 200, 'error_msg': 'access'}})
        assert any('access denied' in r.message for r in caplog.records)

    def test_error_code_901(self, caplog):
        from _dependencies.vk_api_client import _handle_vk_error

        _handle_vk_error({'error': {'error_code': 901, 'error_msg': 'cannot'}})
        assert any('cannot send' in r.message for r in caplog.records)

    def test_error_code_902(self, caplog):
        from _dependencies.vk_api_client import _handle_vk_error

        _handle_vk_error({'error': {'error_code': 902, 'error_msg': 'first'}})
        assert any('first message' in r.message for r in caplog.records)

    def test_error_code_914(self, caplog):
        from _dependencies.vk_api_client import _handle_vk_error

        _handle_vk_error({'error': {'error_code': 914, 'error_msg': 'flood'}})
        assert any('flood control' in r.message for r in caplog.records)

    def test_error_code_917(self, caplog):
        from _dependencies.vk_api_client import _handle_vk_error

        _handle_vk_error({'error': {'error_code': 917, 'error_msg': 'daily'}})
        assert any('per-day' in r.message for r in caplog.records)

    def test_unknown_error_code(self, caplog):
        from _dependencies.vk_api_client import _handle_vk_error

        _handle_vk_error({'error': {'error_code': 999, 'error_msg': 'weird'}})
        assert any('error 999' in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. message_sending.py — VKMessageSender (mocked VKApi)
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKMessageSender:
    """VKMessageSender with mocked VKApi client.

    VKMessageSender now accepts an optional `api` parameter,
    so tests inject a mock directly instead of patching get_default_vk_api_client.
    """

    def test_send_message_success(self, mock_vk_api):
        """Successful send returns message_id."""
        sender = VKMessageSender(api=mock_vk_api)
        result = sender.send_message(peer_id=123, text='hello')

        assert result == 42
        mock_vk_api.send.assert_called_once()

    def test_send_message_with_keyboard(self, mock_vk_api):
        """Send with keyboard parameter."""
        sender = VKMessageSender(api=mock_vk_api)
        keyboard = {'buttons': []}
        sender.send_message(peer_id=1, text='test', keyboard=keyboard)

        mock_vk_api.send.assert_called_once()
        call_kwargs = mock_vk_api.send.call_args[1]
        assert call_kwargs['keyboard'] == keyboard

    def test_send_message_daily_limit(self, mock_vk_api):
        """When daily limit is reached, skip sending."""
        mock_vk_api.send.side_effect = Exception('917')

        sender = VKMessageSender(api=mock_vk_api)
        result = sender.send_message(peer_id=1, text='test')

        assert result is None
        # Second call should be skipped immediately
        result2 = sender.send_message(peer_id=2, text='test2')
        assert result2 is None
        # API should have been called only once
        assert mock_vk_api.send.call_count == 1

    def test_send_message_flood_retry(self, mock_vk_api):
        """Per-minute flood (914) retries up to 3 times."""
        mock_vk_api.send.side_effect = Exception('914')

        sender = VKMessageSender(api=mock_vk_api)
        result = sender.send_message(peer_id=1, text='test')

        assert result is None
        assert mock_vk_api.send.call_count == 3  # 3 attempts

    def test_send_message_flood_then_success(self, mock_vk_api):
        """Flood on first attempt, success on second."""
        mock_vk_api.send.side_effect = [
            Exception('914'),
            {'response': {'message_id': 99}},
        ]

        sender = VKMessageSender(api=mock_vk_api)
        result = sender.send_message(peer_id=1, text='test')

        assert result == 99
        assert mock_vk_api.send.call_count == 2

    def test_send_message_cannot_send_901(self, mock_vk_api):
        """Error 901 (cannot send) returns None without retry."""
        mock_vk_api.send.side_effect = Exception('901')

        sender = VKMessageSender(api=mock_vk_api)
        result = sender.send_message(peer_id=1, text='test')

        assert result is None
        assert mock_vk_api.send.call_count == 1  # no retry

    def test_edit_message_success(self, mock_vk_api):
        sender = VKMessageSender(api=mock_vk_api)
        result = sender.edit_message(peer_id=1, message_id=2, text='new')

        assert result is True
        mock_vk_api.edit_message.assert_called_once_with(peer_id=1, message_id=2, message='new', keyboard=None)

    def test_edit_message_failure(self, mock_vk_api):
        mock_vk_api.edit_message.side_effect = Exception('error')

        sender = VKMessageSender(api=mock_vk_api)
        result = sender.edit_message(peer_id=1, message_id=2, text='new')

        assert result is False

    def test_delete_message_success(self, mock_vk_api):
        sender = VKMessageSender(api=mock_vk_api)
        result = sender.delete_message(peer_id=1, message_ids=[2, 3])

        assert result is True
        mock_vk_api.delete_message.assert_called_once_with(peer_id=1, message_ids=[2, 3])

    def test_delete_message_failure(self, mock_vk_api):
        mock_vk_api.delete_message.side_effect = Exception('error')

        sender = VKMessageSender(api=mock_vk_api)
        result = sender.delete_message(peer_id=1, message_ids=[2])

        assert result is False

    def test_send_callback_answer_success(self, mock_vk_api):
        sender = VKMessageSender(api=mock_vk_api)
        result = sender.send_callback_answer(event_id='evt1', user_id=1, peer_id=2)

        assert result is True
        mock_vk_api.send_message_event_answer.assert_called_once_with(event_id='evt1', user_id=1, peer_id=2)

    def test_send_callback_answer_failure(self, mock_vk_api):
        mock_vk_api.send_message_event_answer.side_effect = Exception('error')

        sender = VKMessageSender(api=mock_vk_api)
        result = sender.send_callback_answer(event_id='evt1', user_id=1, peer_id=2)

        assert result is False

    def test_send_with_keyboard_convenience(self, mock_vk_api):
        """send_with_keyboard creates keyboard and sends."""
        sender = VKMessageSender(api=mock_vk_api)
        result = sender.send_with_keyboard(peer_id=1, text='test', buttons=['A', 'B'])

        assert result == 42
        call_kwargs = mock_vk_api.send.call_args[1]
        assert call_kwargs['keyboard'] is not None
        assert call_kwargs['keyboard']['buttons'][0][0]['action']['label'] == 'A'

    def test_vk_sender_singleton(self):
        """vk_sender() returns the same instance."""
        s1 = vk_sender()
        s2 = vk_sender()
        assert s1 is s2


# ═══════════════════════════════════════════════════════════════════════════════
# 5. database.py — DBClient (with real DB)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDBClient:
    """DBClient with real PostgreSQL connection."""

    @pytest.fixture
    def db_client(self, connection_pool):
        from vk_bot._utils.database import DBClient

        return DBClient(connection_pool)

    def test_get_user_by_vk_id_not_found(self, db_client):
        """Returns None when vk_id doesn't exist."""
        result = db_client.get_user_by_vk_id(-999999)
        assert result is None

    def test_get_user_by_vk_id_found(self, db_client, session):
        """Returns user_id when vk_id exists."""
        import random

        test_vk_id = random.randint(100000, 999999)
        user = db_factories.UserFactory.create_sync(vk_id=str(test_vk_id))
        result = db_client.get_user_by_vk_id(test_vk_id)
        assert result == user.user_id

    def test_set_user_vk_id(self, db_client, session, user_id):
        """set_user_vk_id updates the vk_id column."""
        db_client.set_user_vk_id(user_id, vk_id=99999)
        session.commit()

        from sqlalchemy import text

        with db_client.connect() as conn:
            row = conn.execute(
                text('SELECT vk_id FROM users WHERE user_id = :uid'),
                uid=user_id,
            ).fetchone()
        assert row[0] == '99999'

    def test_is_user_registered_in_vk_true(self, db_client, session):
        import random

        test_vk_id = random.randint(100000, 999999)
        user = db_factories.UserFactory.create_sync(vk_id=str(test_vk_id))
        assert db_client.is_user_registered_in_vk(test_vk_id) is True

    def test_is_user_registered_in_vk_false(self, db_client):
        assert db_client.is_user_registered_in_vk(-999) is False

    def test_resolve_user_id_linked(self, db_client, session):
        """Linked VK user returns telegram user_id."""
        import random

        test_vk_id = random.randint(100000, 999999)
        user = db_factories.UserFactory.create_sync(vk_id=str(test_vk_id))
        result = db_client.resolve_user_id(test_vk_id)
        assert result == user.user_id
        assert result > 0

    def test_resolve_user_id_not_linked(self, db_client):
        """Unlinked VK user returns -vk_user_id."""
        vk_id = 55555
        result = db_client.resolve_user_id(vk_id)
        assert result == -vk_id
        assert result < 0

    def test_settings_property(self, db_client):
        """settings property returns UserSettingsService."""
        from _dependencies.services.user_settings_service import UserSettingsService

        assert isinstance(db_client.settings, UserSettingsService)

    def test_db_singleton(self):
        """db() returns the same instance."""
        from vk_bot._utils.database import db

        d1 = db()
        d2 = db()
        assert d1 is d2


# ═══════════════════════════════════════════════════════════════════════════════
# 6. dispatcher.py — dispatch_event, handle_new_message, handle_callback_event
# ═══════════════════════════════════════════════════════════════════════════════


class TestDispatcherConfirmation:
    """Confirmation handshake."""

    def test_confirmation_valid(self):
        """Valid confirmation returns vk_confirmation_code."""
        result = dispatch_event({'type': 'confirmation', 'group_id': 237036024})
        from _dependencies.commons import get_app_config

        assert result == get_app_config().vk_confirmation_code

    def test_confirmation_invalid_group(self):
        """Invalid group_id returns 'ok'."""
        result = dispatch_event({'type': 'confirmation', 'group_id': 999})
        assert result == 'ok'

    def test_confirmation_missing_group(self):
        """Missing group_id returns 'ok'."""
        result = dispatch_event({'type': 'confirmation'})
        assert result == 'ok'


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

    def test_message_new_unknown_user(self):
        """New user gets registered and receives welcome.

        Uses random vk_user_id to avoid stale data collisions
        (DB is not cleaned between test runs).
        """
        import random as _random

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

        with patch('vk_bot._utils.dispatcher.vk_sender') as mock_sender:
            mock_sender.return_value.send_message.return_value = 1

            result = dispatch_event(event)
            assert result == 'ok'
            # Should have called send_message (welcome text)
            mock_sender.return_value.send_message.assert_called_once()

    def test_message_new_existing_user(self, session):
        """Existing user gets handler chain processing."""
        user = db_factories.UserFactory.create_sync()
        import random as _random

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

        with (
            patch('vk_bot._utils.dispatcher.vk_sender') as mock_sender,
            patch('vk_bot._utils.dispatcher.db') as mock_db,
        ):
            mock_db().resolve_user_id.return_value = user.user_id
            mock_db().settings.check_if_new_user.return_value = False
            mock_sender.return_value.send_message.return_value = 1

            result = dispatch_event(event)
            assert result == 'ok'
            # Should have gone through handler chain (handle_unknown)
            mock_sender.return_value.send_message.assert_called_once()

    def test_message_new_with_state(self, session):
        """User with active state gets handler chain."""
        user = db_factories.UserFactory.create_sync()
        import random as _random

        vk_user_id = _random.randint(1000000, 9999999)

        # Set a state for this user
        set_user_state(user.user_id, DialogState.radius_input)

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

        with (
            patch('vk_bot._utils.dispatcher.vk_sender') as mock_sender,
            patch('vk_bot._utils.dispatcher.db') as mock_db,
        ):
            mock_db().resolve_user_id.return_value = user.user_id
            mock_db().settings.check_if_new_user.return_value = False
            mock_sender.return_value.send_message.return_value = 1

            result = dispatch_event(event)
            assert result == 'ok'

        # Cleanup
        clear_user_state(user.user_id)


class TestDispatcherMessageEvent:
    """message_event (callback) routing."""

    def test_message_event(self):
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

        with patch('vk_bot._utils.dispatcher.vk_sender') as mock_sender:
            mock_sender.return_value.send_callback_answer.return_value = True

            result = dispatch_event(event)
            assert result == 'ok'
            mock_sender.return_value.send_callback_answer.assert_called_once_with(
                event_id='evt_001', user_id=123, peer_id=456
            )

    def test_message_event_without_event_id(self):
        """Callback without event_id still returns ok."""
        event = {
            'type': 'message_event',
            'object': {
                'user_id': 123,
                'peer_id': 456,
            },
        }

        with patch('vk_bot._utils.dispatcher.vk_sender') as mock_sender:
            result = dispatch_event(event)
            assert result == 'ok'
            mock_sender.return_value.send_callback_answer.assert_called_once()


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


class TestHandleUnknown:
    """handle_unknown fallback handler."""

    def test_handle_unknown_returns_result(self):
        from vk_bot._utils.dispatcher import handle_unknown

        msg = VKMessage(text='unknown', user_id=1, peer_id=1)
        result = handle_unknown(msg, None)
        assert result is not None
        assert 'не понимаю' in result.text
        assert result.keyboard is not None

    def test_handle_unknown_with_state(self):
        from vk_bot._utils.dispatcher import handle_unknown

        msg = VKMessage(text='unknown', user_id=1, peer_id=1)
        result = handle_unknown(msg, DialogState.radius_input)
        assert result is not None
        assert 'не понимаю' in result.text


class TestHandlerChain:
    """HANDLER_CHAIN configuration."""

    def test_handler_chain_has_unknown(self):
        """Handler chain contains handle_unknown as fallback."""
        from vk_bot._utils.dispatcher import HANDLER_CHAIN, handle_unknown

        assert handle_unknown in HANDLER_CHAIN
        assert len(HANDLER_CHAIN) >= 1

    def test_handler_chain_last_is_unknown(self):
        """The last handler in chain is handle_unknown."""
        from vk_bot._utils.dispatcher import HANDLER_CHAIN, handle_unknown

        assert HANDLER_CHAIN[-1] is handle_unknown
