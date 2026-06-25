"""Tests for VK Bot API and message sending modules.

These tests cover:
- VKApi.send() with mocked HTTP
- VKApi.edit_message() with mocked HTTP
- VKApi.delete_message() with mocked HTTP
- VKApi.send_message_event_answer() with mocked HTTP
- _handle_vk_error with various error codes
- VKMessageSender (rate limiting, error handling, retries)
"""

import json
from unittest.mock import MagicMock

import pytest

from _dependencies.bot.vk_api_client import VKApi, VkApiError, _handle_vk_error
from vk_bot._utils.message_sending import VKMessageSender

# ═══════════════════════════════════════════════════════════════════════════════
# VKApi.send()
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def vk_sender(mock_vk_api):
    """Create a VKMessageSender with a mocked VKApi client.

    Reduces repeated ``sender = VKMessageSender(api=mock_vk_api)`` in tests.
    """

    return VKMessageSender(api=mock_vk_api)


class TestVKApiSend:
    """VKApi.send() with mocked HTTP."""

    def test_send_basic(self, mock_vk_http):
        """Basic send without optional params."""
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {'message_id': 123}}

        api = VKApi(token='test_token')
        result = api.send(user_id=456, random_id=789, message='hello')

        assert result['response']['message_id'] == 123
        call_kwargs = mock_post.call_args[1]
        data = call_kwargs['data']
        assert data['peer_id'] == 456
        assert data['random_id'] == 789
        assert data['message'] == 'hello'

    def test_send_with_keyboard(self, mock_vk_http):
        """Send with keyboard serialized to JSON."""
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        api = VKApi(token='test_token')
        keyboard = {'one_time': False, 'buttons': []}
        api.send(user_id=1, random_id=1, message='test', keyboard=keyboard)

        call_kwargs = mock_post.call_args[1]
        data = call_kwargs['data']
        assert 'keyboard' in data
        assert json.loads(data['keyboard']) == keyboard

    def test_send_with_attachment(self, mock_vk_http):
        """Send with attachment."""
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        api = VKApi(token='test_token')
        api.send(user_id=1, random_id=1, message='test', attachment='photo123_456')

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['data']['attachment'] == 'photo123_456'

    def test_send_dont_parse_links(self, mock_vk_http):
        """Send with dont_parse_links flag."""
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        api = VKApi(token='test_token')
        api.send(user_id=1, random_id=1, message='https://example.com', dont_parse_links=True)

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['data']['dont_parse_links'] == 1

    def test_send_with_coords(self, mock_vk_http):
        """Send with lat/long."""
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        api = VKApi(token='test_token')
        api.send(user_id=1, random_id=1, message='loc', lat='55.0', long='37.0')

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['data']['lat'] == '55.0'
        assert call_kwargs['data']['long'] == '37.0'


# ═══════════════════════════════════════════════════════════════════════════════
# VKApi.edit_message()
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKApiEditMessage:
    """VKApi.edit_message() with mocked HTTP."""

    def test_edit_basic(self, mock_vk_http):
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        api = VKApi(token='test_token')
        api.edit_message(peer_id=1, message_id=2, message='new text')

        call_kwargs = mock_post.call_args[1]
        data = call_kwargs['data']
        assert data['peer_id'] == 1
        assert data['message_id'] == 2
        assert data['message'] == 'new text'

    def test_edit_with_keyboard(self, mock_vk_http):
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        api = VKApi(token='test_token')
        keyboard = {'buttons': []}
        api.edit_message(peer_id=1, message_id=2, message='text', keyboard=keyboard)

        call_kwargs = mock_post.call_args[1]
        assert 'keyboard' in call_kwargs['data']


# ═══════════════════════════════════════════════════════════════════════════════
# VKApi.delete_message()
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKApiDeleteMessage:
    """VKApi.delete_message() with mocked HTTP."""

    def test_delete(self, mock_vk_http):
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        api = VKApi(token='test_token')
        api.delete_message(peer_id=1, message_ids=[2, 3])

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['params']['peer_id'] == 1
        assert call_kwargs['params']['message_ids'] == '2,3'
        assert call_kwargs['params']['delete_for_all'] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# VKApi.send_message_event_answer()
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKApiSendMessageEventAnswer:
    """VKApi.send_message_event_answer() with mocked HTTP."""

    def test_answer_basic(self, mock_vk_http):
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        api = VKApi(token='test_token')
        api.send_message_event_answer(event_id='evt1', user_id=1, peer_id=2)

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['params']['event_id'] == 'evt1'
        assert call_kwargs['params']['user_id'] == 1
        assert call_kwargs['params']['peer_id'] == 2

    def test_answer_with_event_data(self, mock_vk_http):
        mock_post = mock_vk_http
        mock_post.return_value.json.return_value = {'response': {}}

        api = VKApi(token='test_token')
        event_data = {'type': 'show_snackbar', 'text': 'Done!'}
        api.send_message_event_answer(event_id='evt1', user_id=1, peer_id=2, event_data=event_data)

        call_kwargs = mock_post.call_args[1]
        assert 'event_data' in call_kwargs['json']
        assert json.loads(call_kwargs['json']['event_data']) == event_data


# ═══════════════════════════════════════════════════════════════════════════════
# _handle_vk_error
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKApiErrorHandling:
    """_handle_vk_error with various error codes.

    Now raises VkApiError instead of silently logging.
    """

    def test_no_error(self, caplog):
        _handle_vk_error({'response': {}})
        assert len(caplog.records) == 0

    def test_error_code_1(self, caplog):
        with pytest.raises(VkApiError) as exc_info:
            _handle_vk_error({'error': {'error_code': VkApiError.UNKNOWN_ERROR, 'error_msg': 'unknown'}})
        assert exc_info.value.error_code == VkApiError.UNKNOWN_ERROR
        assert any('unknown error' in r.message for r in caplog.records)

    def test_error_code_100(self, caplog):
        with pytest.raises(VkApiError) as exc_info:
            _handle_vk_error({'error': {'error_code': VkApiError.PARAM_ERROR, 'error_msg': 'param'}})
        assert exc_info.value.error_code == VkApiError.PARAM_ERROR
        assert any('param error' in r.message for r in caplog.records)

    def test_error_code_200(self, caplog):
        with pytest.raises(VkApiError) as exc_info:
            _handle_vk_error({'error': {'error_code': VkApiError.ACCESS_DENIED, 'error_msg': 'access'}})
        assert exc_info.value.error_code == VkApiError.ACCESS_DENIED
        assert any('access denied' in r.message for r in caplog.records)

    def test_error_code_901(self, caplog):
        with pytest.raises(VkApiError) as exc_info:
            _handle_vk_error({'error': {'error_code': VkApiError.CANNOT_SEND_TO_USER, 'error_msg': 'cannot'}})
        assert exc_info.value.error_code == VkApiError.CANNOT_SEND_TO_USER
        assert any('cannot send' in r.message for r in caplog.records)

    def test_error_code_902(self, caplog):
        with pytest.raises(VkApiError) as exc_info:
            _handle_vk_error({'error': {'error_code': VkApiError.CANNOT_SEND_FIRST_MESSAGE, 'error_msg': 'first'}})
        assert exc_info.value.error_code == VkApiError.CANNOT_SEND_FIRST_MESSAGE
        assert any('first message' in r.message for r in caplog.records)

    def test_error_code_914(self, caplog):
        with pytest.raises(VkApiError) as exc_info:
            _handle_vk_error({'error': {'error_code': VkApiError.FLOOD_CONTROL_PER_MINUTE, 'error_msg': 'flood'}})
        assert exc_info.value.error_code == VkApiError.FLOOD_CONTROL_PER_MINUTE
        assert any('flood control' in r.message for r in caplog.records)

    def test_error_code_917(self, caplog):
        with pytest.raises(VkApiError) as exc_info:
            _handle_vk_error({'error': {'error_code': VkApiError.FLOOD_CONTROL_PER_DAY, 'error_msg': 'daily'}})
        assert exc_info.value.error_code == VkApiError.FLOOD_CONTROL_PER_DAY
        assert any('per-day' in r.message for r in caplog.records)

    def test_unknown_error_code(self, caplog):
        with pytest.raises(VkApiError) as exc_info:
            _handle_vk_error({'error': {'error_code': 999, 'error_msg': 'weird'}})
        assert exc_info.value.error_code == 999
        assert any('error 999' in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════════════
# VKMessageSender
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKMessageSender:
    """VKMessageSender with mocked VKApi client.

    VKMessageSender now accepts an optional `api` parameter,
    so tests inject a mock directly instead of patching get_default_vk_api_client.
    """

    def test_send_message_success(self, vk_sender, mock_vk_api):
        """Successful send returns message_id."""
        result = vk_sender.send_message(peer_id=123, text='hello')

        assert result == 42
        mock_vk_api.send.assert_called_once()

    def test_send_message_with_keyboard(self, vk_sender, mock_vk_api):
        """Send with keyboard parameter."""
        keyboard = {'buttons': []}
        vk_sender.send_message(peer_id=1, text='test', keyboard=keyboard)

        mock_vk_api.send.assert_called_once()
        call_kwargs = mock_vk_api.send.call_args[1]
        assert call_kwargs['keyboard'] == keyboard

    def test_send_message_daily_limit(self, vk_sender, mock_vk_api):
        """When daily limit is reached, skip sending."""

        mock_vk_api.send.side_effect = VkApiError(error_code=VkApiError.FLOOD_CONTROL_PER_DAY, error_msg='Daily limit')

        result = vk_sender.send_message(peer_id=1, text='test')

        assert result is None
        # Second call should be skipped immediately
        result2 = vk_sender.send_message(peer_id=2, text='test2')
        assert result2 is None
        # API should have been called only once
        assert mock_vk_api.send.call_count == 1

    def test_send_message_flood_retry(self, vk_sender, mock_vk_api):
        """Per-minute flood (914) retries up to 3 times."""

        mock_vk_api.send.side_effect = VkApiError(error_code=VkApiError.FLOOD_CONTROL_PER_MINUTE, error_msg='Flood')

        result = vk_sender.send_message(peer_id=1, text='test')

        assert result is None
        assert mock_vk_api.send.call_count == 3  # 3 attempts

    def test_send_message_flood_then_success(self, vk_sender, mock_vk_api):
        """Flood on first attempt, success on second."""

        mock_vk_api.send.side_effect = [
            VkApiError(error_code=VkApiError.FLOOD_CONTROL_PER_MINUTE, error_msg='Flood'),
            {'response': {'message_id': 99}},
        ]

        result = vk_sender.send_message(peer_id=1, text='test')

        assert result == 99
        assert mock_vk_api.send.call_count == 2

    def test_send_message_cannot_send_901(self, vk_sender, mock_vk_api):
        """Error 901 (cannot send) returns None without retry."""

        mock_vk_api.send.side_effect = VkApiError(error_code=VkApiError.CANNOT_SEND_TO_USER, error_msg='Cannot send')

        result = vk_sender.send_message(peer_id=1, text='test')

        assert result is None
        assert mock_vk_api.send.call_count == 1  # no retry

    def test_edit_message_success(self, vk_sender, mock_vk_api):
        result = vk_sender.edit_message(peer_id=1, message_id=2, text='new')

        assert result is True
        mock_vk_api.edit_message.assert_called_once_with(
            peer_id=1, message_id=2, message='new', keyboard=None, conversation_message_id=None
        )

    def test_edit_message_failure(self, vk_sender, mock_vk_api):
        mock_vk_api.edit_message.side_effect = Exception('error')

        result = vk_sender.edit_message(peer_id=1, message_id=2, text='new')

        assert result is False

    def test_delete_message_success(self, vk_sender, mock_vk_api):
        result = vk_sender.delete_message(peer_id=1, message_ids=[2, 3])

        assert result is True
        mock_vk_api.delete_message.assert_called_once_with(peer_id=1, message_ids=[2, 3])

    def test_delete_message_failure(self, vk_sender, mock_vk_api):
        mock_vk_api.delete_message.side_effect = Exception('error')

        result = vk_sender.delete_message(peer_id=1, message_ids=[2])

        assert result is False

    def test_send_callback_answer_success(self, vk_sender, mock_vk_api):
        result = vk_sender.send_callback_answer(event_id='evt1', user_id=1, peer_id=2)

        assert result is True
        mock_vk_api.send_message_event_answer.assert_called_once_with(
            event_id='evt1',
            user_id=1,
            peer_id=2,
            event_data=None,
        )

    def test_send_callback_answer_failure(self, vk_sender, mock_vk_api):
        mock_vk_api.send_message_event_answer.side_effect = Exception('error')

        result = vk_sender.send_callback_answer(event_id='evt1', user_id=1, peer_id=2)

        assert result is False

    def test_send_with_keyboard_convenience(self, vk_sender, mock_vk_api):
        """send_with_keyboard creates keyboard and sends."""
        result = vk_sender.send_with_keyboard(peer_id=1, text='test', buttons=['A', 'B'])

        assert result == 42
        call_kwargs = mock_vk_api.send.call_args[1]
        assert call_kwargs['keyboard'] is not None
        assert call_kwargs['keyboard']['buttons'][0][0]['action']['label'] == 'A'
