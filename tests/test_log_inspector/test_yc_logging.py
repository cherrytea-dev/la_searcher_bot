"""Tests for YC Log Inspector — gRPC-based YC Logging client."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from google.protobuf.timestamp_pb2 import Timestamp
from yandex.cloud.logging.v1.log_entry_pb2 import LogEntry, LogLevel
from yandex.cloud.logging.v1.log_group_service_pb2 import (
    ListLogGroupsRequest,
)
from yandex.cloud.logging.v1.log_group_service_pb2_grpc import LogGroupServiceStub
from yandex.cloud.logging.v1.log_reading_service_pb2_grpc import LogReadingServiceStub

from tools.log_inspector._utils.yc_logging import (
    AuthError,
    LogGroup,
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
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_sdk() -> MagicMock:
    """Create a mock SDK with mock gRPC stubs."""
    sdk = MagicMock()
    sdk.client = MagicMock()
    return sdk


def _make_entry(uid: str, level: int, message: str, timestamp: datetime) -> MagicMock:
    """Create a mock LogEntry-like object."""
    entry = MagicMock(spec=LogEntry)
    entry.uid = uid
    entry.level = level
    entry.message = message

    ts_proto = Timestamp()
    ts_proto.FromDatetime(timestamp)
    entry.timestamp = ts_proto

    entry.stream_name = ''
    entry.HasField.return_value = False
    entry.json_payload = None
    return entry


def _make_log_group(id_: str, name: str, folder_id: str) -> MagicMock:
    """Create a mock log group protobuf message."""
    g = MagicMock()
    g.id = id_
    g.name = name
    g.folder_id = folder_id
    return g


# ---------------------------------------------------------------------------
# YCLoggingClient — Auth
# ---------------------------------------------------------------------------


class TestYCLoggingClientAuth:
    def test_fails_without_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv('YC_LOG_INSPECTOR_SA_JSON', raising=False)
        with pytest.raises(AuthError, match='YC_LOG_INSPECTOR_SA_JSON'):
            YCLoggingClient()

    def test_uses_sa_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('YC_LOG_INSPECTOR_SA_JSON', json.dumps(SERVICE_ACCOUNT_KEY))

        with patch('tools.log_inspector._utils.yc_logging.SDK') as mock_sdk_cls:
            client = YCLoggingClient()
            mock_sdk_cls.assert_called_once_with(service_account_key=SERVICE_ACCOUNT_KEY)
            assert client._sdk is not None


# ---------------------------------------------------------------------------
# YCLoggingClient — Log Groups
# ---------------------------------------------------------------------------


class TestListLogGroups:
    def test_lists_groups(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('YC_LOG_INSPECTOR_SA_JSON', json.dumps(SERVICE_ACCOUNT_KEY))

        mock_sdk = _make_mock_sdk()
        mock_stub = MagicMock()
        mock_group_1 = _make_log_group('lg-001', 'bot-logs', 'fc-test')
        mock_group_2 = _make_log_group('lg-002', 'api-logs', 'fc-test')

        resp = MagicMock()
        resp.groups = [mock_group_1, mock_group_2]
        mock_stub.List.return_value = resp

        def client_side_effect(stub_cls):
            if stub_cls == LogGroupServiceStub:
                return mock_stub
            return MagicMock()

        mock_sdk.client.side_effect = client_side_effect

        with patch('tools.log_inspector._utils.yc_logging.SDK', return_value=mock_sdk):
            client = YCLoggingClient()
            groups = client.list_log_groups('fc-test')

        assert len(groups) == 2
        assert groups[0] == LogGroup(id='lg-001', name='bot-logs', folder_id='fc-test')
        assert groups[1] == LogGroup(id='lg-002', name='api-logs', folder_id='fc-test')
        mock_stub.List.assert_called_once_with(ListLogGroupsRequest(folder_id='fc-test'))


# ---------------------------------------------------------------------------
# YCLoggingClient — Read Logs
# ---------------------------------------------------------------------------


class TestReadLogs:
    def test_read_single_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('YC_LOG_INSPECTOR_SA_JSON', json.dumps(SERVICE_ACCOUNT_KEY))

        mock_sdk = _make_mock_sdk()
        mock_reading_stub = MagicMock()
        mock_group_stub = MagicMock()

        now = datetime(2026, 7, 4, 18, 0, 0, tzinfo=timezone.utc)
        entry = _make_entry('uid-1', LogLevel.ERROR, 'something broke', now)

        read_resp = MagicMock()
        read_resp.entries = [entry]
        read_resp.next_page_token = 'page2'
        mock_reading_stub.Read.return_value = read_resp

        def client_side_effect(stub_cls):
            if stub_cls == LogGroupServiceStub:
                return mock_group_stub
            if stub_cls == LogReadingServiceStub:
                return mock_reading_stub
            return MagicMock()

        mock_sdk.client.side_effect = client_side_effect

        with patch('tools.log_inspector._utils.yc_logging.SDK', return_value=mock_sdk):
            client = YCLoggingClient()
            result = client.read_logs('lg-xxx', levels=['ERROR'])

        assert len(result['entries']) == 1
        assert result['next_page_token'] == 'page2'
        assert result['entries'][0]['uid'] == 'uid-1'
        assert result['entries'][0]['level'] == 'ERROR'
        assert result['entries'][0]['message'] == 'something broke'

    def test_read_all_logs_paginates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('YC_LOG_INSPECTOR_SA_JSON', json.dumps(SERVICE_ACCOUNT_KEY))

        mock_sdk = _make_mock_sdk()
        mock_reading_stub = MagicMock()
        mock_group_stub = MagicMock()

        now = datetime(2026, 7, 4, 18, 0, 0, tzinfo=timezone.utc)

        resp_1 = MagicMock()
        resp_1.entries = [_make_entry('uid-1', LogLevel.ERROR, 'err1', now)]
        resp_1.next_page_token = 'p2'

        resp_2 = MagicMock()
        resp_2.entries = [_make_entry('uid-2', LogLevel.ERROR, 'err2', now)]
        resp_2.next_page_token = ''

        mock_reading_stub.Read.side_effect = [resp_1, resp_2]

        def client_side_effect(stub_cls):
            if stub_cls == LogGroupServiceStub:
                return mock_group_stub
            if stub_cls == LogReadingServiceStub:
                return mock_reading_stub
            return MagicMock()

        mock_sdk.client.side_effect = client_side_effect

        with patch('tools.log_inspector._utils.yc_logging.SDK', return_value=mock_sdk):
            client = YCLoggingClient()
            entries = client.read_all_logs('lg-xxx')

        assert len(entries) == 2

    def test_read_all_logs_respects_max_pages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('YC_LOG_INSPECTOR_SA_JSON', json.dumps(SERVICE_ACCOUNT_KEY))

        mock_sdk = _make_mock_sdk()
        mock_reading_stub = MagicMock()
        mock_group_stub = MagicMock()

        now = datetime(2026, 7, 4, 18, 0, 0, tzinfo=timezone.utc)

        resp = MagicMock()
        resp.entries = [_make_entry('uid-1', LogLevel.INFO, 'msg', now)]
        resp.next_page_token = 'still-more'

        mock_reading_stub.Read.return_value = resp

        def client_side_effect(stub_cls):
            if stub_cls == LogGroupServiceStub:
                return mock_group_stub
            if stub_cls == LogReadingServiceStub:
                return mock_reading_stub
            return MagicMock()

        mock_sdk.client.side_effect = client_side_effect

        with patch('tools.log_inspector._utils.yc_logging.SDK', return_value=mock_sdk):
            client = YCLoggingClient()
            entries = client.read_all_logs('lg-xxx', max_pages=2)

        assert len(entries) == 2

    def test_passes_time_range(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('YC_LOG_INSPECTOR_SA_JSON', json.dumps(SERVICE_ACCOUNT_KEY))

        mock_sdk = _make_mock_sdk()
        mock_reading_stub = MagicMock()
        mock_group_stub = MagicMock()

        from_time = datetime(2026, 7, 4, 0, 0, 0, tzinfo=timezone.utc)

        resp = MagicMock()
        resp.entries = []
        resp.next_page_token = ''
        mock_reading_stub.Read.return_value = resp

        def client_side_effect(stub_cls):
            if stub_cls == LogGroupServiceStub:
                return mock_group_stub
            if stub_cls == LogReadingServiceStub:
                return mock_reading_stub
            return MagicMock()

        mock_sdk.client.side_effect = client_side_effect

        with patch('tools.log_inspector._utils.yc_logging.SDK', return_value=mock_sdk):
            client = YCLoggingClient()
            client.read_logs('lg-x', from_time=from_time)

        call_args = mock_reading_stub.Read.call_args
        request = call_args[0][0]
        assert request.HasField('criteria')
        # Proto Timestamp.ToDatetime() returns naive UTC
        assert request.criteria.since.ToDatetime() == from_time.replace(tzinfo=None)

    def test_uses_page_token_when_provided(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('YC_LOG_INSPECTOR_SA_JSON', json.dumps(SERVICE_ACCOUNT_KEY))

        mock_sdk = _make_mock_sdk()
        mock_reading_stub = MagicMock()
        mock_group_stub = MagicMock()

        resp = MagicMock()
        resp.entries = []
        resp.next_page_token = ''
        mock_reading_stub.Read.return_value = resp

        def client_side_effect(stub_cls):
            if stub_cls == LogGroupServiceStub:
                return mock_group_stub
            if stub_cls == LogReadingServiceStub:
                return mock_reading_stub
            return MagicMock()

        mock_sdk.client.side_effect = client_side_effect

        with patch('tools.log_inspector._utils.yc_logging.SDK', return_value=mock_sdk):
            client = YCLoggingClient()
            client.read_logs('lg-x', page_token='next-page')

        call_args = mock_reading_stub.Read.call_args
        request = call_args[0][0]
        assert request.page_token == 'next-page'
        assert not request.HasField('criteria')
