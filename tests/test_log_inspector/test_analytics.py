"""Tests for YC Log Inspector — analytics module."""

from tools.log_inspector._utils.analytics import (
    extract_request_id,
    group_errors,
    normalize_error,
)


class TestNormalizeError:
    def test_replaces_uuid_single_quoted(self) -> None:
        result = normalize_error("Error: '550e8400-e29b-41d4-a716-446655440000' not found")
        assert '<uuid>' in result
        assert '550e8400' not in result

    def test_replaces_uuid_double_quoted(self) -> None:
        result = normalize_error('Error: "550e8400-e29b-41d4-a716-446655440000" not found')
        assert '<uuid>' in result
        assert '550e8400' not in result

    def test_replaces_ip(self) -> None:
        result = normalize_error('Connection to 192.168.1.100 failed')
        assert '<ip>' in result
        assert '192.168.1.100' not in result

    def test_replaces_timestamp(self) -> None:
        result = normalize_error('at 2026-07-04T18:30:00 something happened')
        assert '<timestamp>' in result
        # Only the date/time part, not the whole line
        assert 'something happened' in result

    def test_replaces_hash(self) -> None:
        result = normalize_error('checksum abcdef0123456789abcdef0123456789 mismatch')
        assert '<hash>' in result

    def test_replaces_hex(self) -> None:
        result = normalize_error('pointer 0x7f8a1b2c3d4e was accessed')
        assert '<hex>' in result

    def test_replaces_large_number(self) -> None:
        result = normalize_error('id 123456789012345 not found')
        assert '<large_num>' in result

    def test_replaces_telegram_id(self) -> None:
        result = normalize_error('telegram_id=12345 not found')
        assert 'telegram_id=<id>' in result

    def test_handles_empty_string(self) -> None:
        assert normalize_error('') == ''

    def test_returns_unmatched_text(self) -> None:
        assert normalize_error('plain text without variables') == 'plain text without variables'


class TestExtractRequestId:
    def test_from_json_payload(self) -> None:
        entry = {
            'json_payload': {'request_id': 'abc-123-def'},
            'message': '',
        }
        assert extract_request_id(entry) == 'abc-123-def'

    def test_from_message(self) -> None:
        entry = {
            'json_payload': {},
            'message': 'Error [request_id: abc-123-def] something broke',
        }
        assert extract_request_id(entry) == 'abc-123-def'

    def test_from_message_with_equals(self) -> None:
        entry = {
            'json_payload': {},
            'message': 'request_id=abc-123-def error detail',
        }
        assert extract_request_id(entry) == 'abc-123-def'

    def test_not_found(self) -> None:
        entry = {'message': 'no request id here'}
        assert extract_request_id(entry) is None

    def test_json_payload_not_dict(self) -> None:
        entry = {'json_payload': 'string_value', 'message': 'text'}
        assert extract_request_id(entry) is None


class TestGroupErrors:
    def test_groups_identical_errors(self) -> None:
        entries = [
            {'level': 'ERROR', 'message': "key '550e8400-e29b-41d4-a716-446655440000' not found"},
            {'level': 'ERROR', 'message': "key '660e8400-e29b-41d4-a716-446655440001' not found"},
            {'level': 'ERROR', 'message': "key '770e8400-e29b-41d4-a716-446655440002' not found"},
        ]
        groups = group_errors(entries)
        assert len(groups) == 1
        assert groups[0].count == 3

    def test_sorts_by_count_descending(self) -> None:
        entries = [
            *[{'level': 'ERROR', 'message': 'rare error'}] * 1,
            *[{'level': 'ERROR', 'message': 'common error'}] * 5,
            *[{'level': 'ERROR', 'message': 'medium error'}] * 3,
        ]
        groups = group_errors(entries)
        assert groups[0].count == 5
        assert groups[1].count == 3
        assert groups[2].count == 1

    def test_stores_sample_request_ids(self) -> None:
        entries = [
            {
                'level': 'ERROR',
                'message': 'error',
                'json_payload': {'request_id': 'req-1'},
            },
            {
                'level': 'ERROR',
                'message': 'error',
                'json_payload': {'request_id': 'req-2'},
            },
        ]
        groups = group_errors(entries, max_request_ids=3)
        assert len(groups[0].sample_request_ids) == 2

    def test_respects_max_request_ids(self) -> None:
        entries = [
            {
                'level': 'ERROR',
                'message': 'error',
                'json_payload': {'request_id': f'req-{i}'},
            }
            for i in range(10)
        ]
        groups = group_errors(entries, max_request_ids=2)
        assert len(groups[0].sample_request_ids) <= 2

    def test_filters_non_error_levels(self) -> None:
        entries = [
            {'level': 'ERROR', 'message': 'err'},
            {'level': 'INFO', 'message': 'info'},
            {'level': 'WARN', 'message': 'warn'},
        ]
        groups = group_errors(entries)
        assert len(groups) == 1
        assert groups[0].count == 1

    def test_empty_on_missing_level(self) -> None:
        entries = [{'message': 'no level field'}]
        assert group_errors(entries) == []

    def test_empty_entries(self) -> None:
        assert group_errors([]) == []

    def test_preserves_sample_message(self) -> None:
        real_message = 'the original error text'
        entries = [
            {'level': 'ERROR', 'message': real_message},
        ]
        groups = group_errors(entries)
        assert groups[0].sample_message == real_message
