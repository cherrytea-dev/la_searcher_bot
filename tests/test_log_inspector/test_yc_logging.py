"""Tests for YC Log Inspector — YC Logging API client."""

import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from tools.log_inspector._utils.yc_logging import (
    AuthError,
    IamTokenAuth,
    YCLoggingClient,
)

SERVICE_ACCOUNT_KEY = {
    'id': 'aje123abc',
    'service_account_id': 'ajefake00000000000000000',
    'private_key': (
        '-----BEGIN PRIVATE KEY-----\n'
        'MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC+Z2iyBEqRnXFp\n'
        'rP/oDXFTo12kpNfFdoe4qS0QUjvfcy1a3UEx6rd9E0USWCXhHNL2BKosb6xGN1H4\n'
        'W7IQ4RFmbsZBRFGFa0eERJqCmLxuL0SKGCcBjfa7A+mhQ09cEu+iZf2VLA6FBsI/\n'
        'rbcJPR4wTyDnzCYIpFJfUtWxrHWIVMYOlSHbX1brdYk3wYkq7g5TICb0phEGvPI8\n'
        'k//hweR7ugl66e0VJ8Jm5WuMCrBwICXxqI2PnR+b7lMUB9lscR48jH3pqEfWxHTR\n'
        '+TD4kEK/D5YmtqK4EvqNntS0McfYms0EjiFhO1bJWcNApV5aZGWmyaNlmMRU6JY6\n'
        'NR/aemAlAgMBAAECggEAJxHn0ZfJhIHJMEB7hLLUo4Bgf1fgT1FgQjUChOgKNEfI\n'
        'XhHyVWUks0K/1RyNt68l3lNw5k5IZBB1kO+RdNu3VHyUlR02DZLPmEnXVBC/y/JN\n'
        'Fcd/wbqLKyMvD0kUnN7b5YM9cnrPKcFfYyZP1G3KqOsvRKlY4YXoNLCNmF8LK7nA\n'
        'NvBxVzPcxuLwAY2NcxKs3A3RXFNs1Ibyq6xV1R0HCPmWvYOlYWJMNmC3aJ2K5YpN\n'
        'Y8pO9cQKgEYiM4OFRUJBRE2EWNS9iJDy8HZ1B8J4E1kEqHzU5nVMARXC5DoXyT8S\n'
        'b1BGjB8xRJcvLt1F3yLd0C9M/xJvYDCiIZ/E7p/1YQKBgQDk/c2kBGbzLtKRyFQ+\n'
        'L5QRXNhXMKJRXJcEUYGQKLMqBj6iHDHcOENXcH0tckMXhOULZNxhJOm9jDFULrGH\n'
        'e0PwSHaPlVJ5Kzm8qC/KNQmJXNPiOHBqLvGPiMGcXnUSoCcU5LqAJYBvWoC8ACU4\n'
        'k9jTKyJhYk0YIRZYHKGgMcViMwKBgQDU7XKUoJ4SIgiALpNXF6BLODkSyJ3XMO4q\n'
        '0RpJhNXIJGHCqKL4iKZQOPSzLukSWXy3YKJvJXfqo2JiFMWXJkZLpJBgZIBWBFP/\n'
        '6ETR+FIcDKHK8Q3pCrqHOcmJK8TayFZOFYlXZUMkySVYbOqKdBMRPMuLSpPJkByF\n'
        '3ViGSSQVWwKBgQC3sJi/JEUkzAocpGpovQIJVpFsNaURBgxHRFMSMfQhhYDf7OAM\n'
        'lWPLN7BUmgPtFfDnBzE3F/FoGRAiKhJTm0KFaIyG1HrHBS+GlISg7aHrvBf4T1H+\n'
        'rBMuwKlEuEU6BJHpDFoWlqMLAu1r4XkXAQfMeAhCYUcVjpK5YN0cGLHtMQKBgBN3\n'
        '3QmR+oJoKxso6VFJWHiARqRHPCx+YvYEMRQU0WGa8B1UHXmB4ILK2/StC0nO4q4T\n'
        'MVJTMaEBQkpqgUW5wJG0UoNvVTcZIHgLFzqCKk+RMKZcJQ5IQe1Z3Dq6CSGIKKBk\n'
        'FNWaNHYLPlNYPbqSB2JHk1QmSmCWlQvkh7iSli/rAoGAdK5uJHqZYUJ5DQs4qKg7\n'
        'WLQd3XVTFBbN9JHiR/YcPqCwILAtYmWZR4CUqUNZYKTk0JvjxPsUUovYyB46YYJ6\n'
        'KTrFhPx5KqPWWoNPB2kKZLbsdEUszNBDIlLJoxWFCyqQnZgWHQtGGQhSMPMKqk1U\n'
        'nHOKH4YHXLBMFUPfpjHYuWs=\n'
        '-----END PRIVATE KEY-----\n'
    ),
}


# ---------------------------------------------------------------------------
# IamTokenAuth
# ---------------------------------------------------------------------------


class TestIamTokenAuth:
    def test_uses_sa_json_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('YC_SERVICE_ACCOUNT_JSON', json.dumps(SERVICE_ACCOUNT_KEY))

        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            'iamToken': 't1.sa...xyz',
            'expiresAt': '2099-01-01T00:00:00Z',
        }

        with (
            patch.object(IamTokenAuth, '_make_jwt', return_value='mock-jwt-token') as mock_jwt,
            patch('httpx.post', return_value=mock_resp) as mock_post,
        ):
            auth = IamTokenAuth()
            token = auth.get_token()
            assert token == 't1.sa...xyz'
            mock_jwt.assert_called_once()
            mock_post.assert_called_once()

    def test_caches_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('YC_SERVICE_ACCOUNT_JSON', json.dumps(SERVICE_ACCOUNT_KEY))

        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {'iamToken': 't1.sa...xyz'}

        with (
            patch('httpx.post', return_value=mock_resp) as mock_post,
            patch.object(IamTokenAuth, '_make_jwt', return_value='mock-jwt'),
        ):
            auth = IamTokenAuth()
            auth.get_token()
            assert mock_post.call_count == 1

            # Second call should use cache
            auth.get_token()
            assert mock_post.call_count == 1

    def test_fails_without_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv('YC_SERVICE_ACCOUNT_JSON', raising=False)
        with pytest.raises(AuthError, match='YC_SERVICE_ACCOUNT_JSON'):
            IamTokenAuth().get_token()

    def test_invalidate_clears_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('YC_SERVICE_ACCOUNT_JSON', json.dumps(SERVICE_ACCOUNT_KEY))

        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {'iamToken': 't1.sa...xyz'}

        with (
            patch('httpx.post', return_value=mock_resp) as mock_post,
            patch.object(IamTokenAuth, '_make_jwt', return_value='mock-jwt'),
        ):
            auth = IamTokenAuth()
            auth.get_token()
            assert mock_post.call_count == 1

            auth.invalidate()
            auth.get_token()
            assert mock_post.call_count == 2


# ---------------------------------------------------------------------------
# YCLoggingClient
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> YCLoggingClient:
    """Return a client with a mocked auth that always returns 'test-token'."""
    auth = Mock(spec=IamTokenAuth)
    auth.get_token.return_value = 'test-token'
    return YCLoggingClient(auth=auth)


def _mock_response(json_data: dict, status: int = 200) -> Mock:
    """Build a mock HTTP response."""
    resp = Mock()
    resp.status_code = status
    resp.raise_for_status = Mock()
    resp.json.return_value = json_data
    return resp


class TestYCLoggingClient:
    def test_list_log_groups(self, client: YCLoggingClient) -> None:
        mock_resp = _mock_response(
            {
                'groups': [
                    {'id': 'lg-001', 'name': 'bot-logs', 'folderId': 'fc-test'},
                    {'id': 'lg-002', 'name': 'api-logs', 'folderId': 'fc-test'},
                ],
            }
        )

        with patch.object(client._http, 'request', return_value=mock_resp) as mock_request:
            groups = client.list_log_groups('fc-test')
            assert len(groups) == 2
            assert groups[0].id == 'lg-001'
            assert groups[0].name == 'bot-logs'
            mock_request.assert_called_once()

    def test_read_single_page(self, client: YCLoggingClient) -> None:
        mock_resp = _mock_response(
            {
                'entries': [
                    {
                        'uid': '1',
                        'level': 'ERROR',
                        'message': 'something broke',
                        'timestamp': '2026-07-04T18:00:00Z',
                    },
                ],
                'next_page_token': 'page2',
            }
        )

        with patch.object(client._http, 'request', return_value=mock_resp) as mock_request:
            result = client.read_logs('lg-xxx', levels=['ERROR'])
            assert len(result['entries']) == 1
            assert result['next_page_token'] == 'page2'
            mock_request.assert_called_once()

    def test_read_all_logs_paginates(self, client: YCLoggingClient) -> None:
        page_1_resp = _mock_response(
            {
                'entries': [
                    {'uid': '1', 'level': 'ERROR', 'message': 'err1', 'timestamp': 't1'},
                ],
                'next_page_token': 'p2',
            }
        )
        page_2_resp = _mock_response(
            {
                'entries': [
                    {'uid': '2', 'level': 'ERROR', 'message': 'err2', 'timestamp': 't2'},
                ],
            }
        )

        with patch.object(client._http, 'request', side_effect=[page_1_resp, page_2_resp]):
            entries = client.read_all_logs('lg-xxx')
            assert len(entries) == 2

    def test_read_all_logs_respects_max_pages(self, client: YCLoggingClient) -> None:
        page_resp = _mock_response(
            {
                'entries': [
                    {'uid': '1', 'level': 'INFO', 'message': 'msg', 'timestamp': 't'},
                ],
                'next_page_token': 'still-more',
            }
        )

        with patch.object(client._http, 'request', return_value=page_resp):
            entries = client.read_all_logs('lg-xxx', max_pages=2)
            assert len(entries) == 2

    def test_passes_time_range(self, client: YCLoggingClient) -> None:
        from_time = datetime(2026, 7, 4, 0, 0, 0, tzinfo=timezone.utc)
        mock_resp = _mock_response({'entries': []})

        with patch.object(client._http, 'request', return_value=mock_resp) as mock_request:
            client.read_logs('lg-x', from_time=from_time)
            call_args = mock_request.call_args
            body = call_args[1]['json']
            assert body['from'] == '2026-07-04T00:00:00Z'

    def test_retries_on_401(self, client: YCLoggingClient) -> None:
        """Should refresh token on 401 and retry the request once."""
        fail_resp = _mock_response({'error': 'unauthorized'}, status=401)
        ok_resp = _mock_response(
            {
                'entries': [
                    {'uid': '1', 'level': 'ERROR', 'message': 'ok after retry', 'timestamp': 't1'},
                ],
            }
        )

        with patch.object(client._http, 'request', side_effect=[fail_resp, ok_resp]):
            result = client.read_logs('lg-x', levels=['ERROR'])
            assert len(result['entries']) == 1
            assert result['entries'][0]['message'] == 'ok after retry'
