"""Tests for YC Log Inspector — YC Logging API client."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from tools.log_inspector._utils.yc_logging import (
    YCLoggingClient,
    get_iam_token,
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
# get_iam_token
# ---------------------------------------------------------------------------


class TestGetIamToken:
    def test_uses_yc_iam_token_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('YC_IAM_TOKEN', 't1.efa...abc')
        assert get_iam_token() == 't1.efa...abc'

    def test_uses_sa_json_with_iam_exchange(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv('YC_IAM_TOKEN', raising=False)
        monkeypatch.setenv('YC_LOG_INSPECTOR_SA_JSON', '{"id": "aje123"}')

        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            'iamToken': 't1.sa...xyz',
            'expiresAt': '2099-01-01T00:00:00Z',
        }

        with (
            patch(
                'tools.log_inspector._utils.yc_logging._make_jwt',
                return_value='mock-jwt-token',
            ) as mock_jwt,
            patch('httpx.post', return_value=mock_resp) as mock_post,
        ):
            token = get_iam_token()
            assert token == 't1.sa...xyz'
            mock_jwt.assert_called_once()
            mock_post.assert_called_once()

    def test_fails_without_any_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv('YC_IAM_TOKEN', raising=False)
        monkeypatch.delenv('YC_LOG_INSPECTOR_SA_JSON', raising=False)

        with patch('httpx.get', side_effect=Exception('no metadata')):
            with pytest.raises(RuntimeError, match='No auth method'):
                get_iam_token()


# ---------------------------------------------------------------------------
# YCLoggingClient
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> YCLoggingClient:
    return YCLoggingClient(iam_token='test-token')


class TestYCLoggingClient:
    def test_list_log_groups(self, client: YCLoggingClient) -> None:
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            'groups': [
                {'id': 'lg-001', 'name': 'bot-logs', 'folderId': 'fc-test'},
                {'id': 'lg-002', 'name': 'api-logs', 'folderId': 'fc-test'},
            ],
        }

        with patch.object(client._client, 'get', return_value=mock_resp) as mock_get:
            groups = client.list_log_groups('fc-test')
            assert len(groups) == 2
            assert groups[0].id == 'lg-001'
            assert groups[0].name == 'bot-logs'
            mock_get.assert_called_once()

    def test_read_single_page(self, client: YCLoggingClient) -> None:
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
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

        with patch.object(client._client, 'post', return_value=mock_resp) as mock_post:
            result = client.read_logs('lg-xxx', levels=['ERROR'])
            assert len(result['entries']) == 1
            assert result['next_page_token'] == 'page2'
            mock_post.assert_called_once()

    def test_read_all_logs_paginates(self, client: YCLoggingClient) -> None:
        page_1_resp = Mock()
        page_1_resp.raise_for_status = Mock()
        page_1_resp.json.return_value = {
            'entries': [
                {'uid': '1', 'level': 'ERROR', 'message': 'err1', 'timestamp': 't1'},
            ],
            'next_page_token': 'p2',
        }
        page_2_resp = Mock()
        page_2_resp.raise_for_status = Mock()
        page_2_resp.json.return_value = {
            'entries': [
                {'uid': '2', 'level': 'ERROR', 'message': 'err2', 'timestamp': 't2'},
            ],
        }

        with patch.object(client._client, 'post', side_effect=[page_1_resp, page_2_resp]):
            entries = client.read_all_logs('lg-xxx')
            assert len(entries) == 2

    def test_read_all_logs_respects_max_pages(self, client: YCLoggingClient) -> None:
        page_resp = Mock()
        page_resp.raise_for_status = Mock()
        page_resp.json.return_value = {
            'entries': [
                {'uid': '1', 'level': 'INFO', 'message': 'msg', 'timestamp': 't'},
            ],
            'next_page_token': 'still-more',
        }

        with patch.object(client._client, 'post', return_value=page_resp):
            entries = client.read_all_logs('lg-xxx', max_pages=2)
            assert len(entries) == 2

    def test_passes_time_range(self, client: YCLoggingClient) -> None:
        from_time = datetime(2026, 7, 4, 0, 0, 0, tzinfo=timezone.utc)

        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {'entries': []}

        with patch.object(client._client, 'post', return_value=mock_resp) as mock_post:
            client.read_logs('lg-x', from_time=from_time)
            call_args = mock_post.call_args
            body = call_args[1]['json']
            assert body['from'] == '2026-07-04T00:00:00Z'
