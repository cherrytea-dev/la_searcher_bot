"""Error analytics: grouping, frequency analysis, request_id extraction."""

import logging
import re
from collections import Counter
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)


class ErrorGroup:
    """A group of identical or similar errors."""

    def __init__(self, pattern: str, sample_entry: dict, count: int) -> None:
        self.pattern = pattern
        self.sample_entry = sample_entry
        self.count = count
        self.sample_request_id: str | None = _extract_request_id(sample_entry)

    def __repr__(self) -> str:
        return f'ErrorGroup(pattern={self.pattern!r}, count={self.count})'


def _extract_request_id(entry: dict) -> str | None:
    """Extract request_id from a log entry, checking multiple locations."""
    # Yandex Cloud Functions put request_id in json_payload.request_id
    payload = entry.get('jsonPayload') or entry.get('json_payload') or {}
    if isinstance(payload, dict):
        rid = payload.get('request_id') or payload.get('requestId')
        if rid:
            return str(rid)

    # Also check top-level fields
    rid = entry.get('request_id') or entry.get('requestId')
    if rid:
        return str(rid)

    # Try to find it in the message text
    message = _get_message(entry)
    match = re.search(r'request_id[=:]\s*(\S+)', message)
    if match:
        return match.group(1)

    return None


def _normalize_error(message: str) -> str:
    """Normalize error message to group similar errors together.

    Replaces variable parts (IDs, timestamps, numbers) with placeholders.
    """
    # Remove traceback details (file paths, line numbers)
    msg = re.sub(r'File "[^"]+", line \d+', '<file>:<line>', message)
    # Replace UUIDs
    msg = re.sub(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        '<uuid>',
        msg,
    )
    # Replace request IDs
    msg = re.sub(r'(request_id|requestId)[=:]\s*\S+', r'\1=<id>', msg)
    # Replace trace/span IDs
    msg = re.sub(r'(trace_id|span_id|traceId|spanId)[=:]\s*\S+', r'\1=<id>', msg)
    # Replace SQL parameters (numbers after values)
    msg = re.sub(r'\b\d{4,}\b', '<num>', msg)
    # Replace hex addresses
    msg = re.sub(r'0x[0-9a-fA-F]+', '<hex>', msg)
    # Collapse multiple spaces
    msg = re.sub(r'\s+', ' ', msg).strip()
    return msg


def _get_message(entry: dict) -> str:
    """Extract the text message from a log entry."""
    # Yandex Cloud Logging format: jsonPayload.textPayload or jsonPayload.message
    payload = entry.get('jsonPayload') or entry.get('json_payload') or {}
    if isinstance(payload, dict):
        return payload.get('textPayload') or payload.get('message') or payload.get('text_payload') or ''
    return str(entry.get('message', ''))


def _get_level(entry: dict) -> str:
    """Extract log level from an entry."""
    return (entry.get('level') or entry.get('severity') or 'UNKNOWN').upper()


def group_errors(entries: list[dict], top_n: int = 10) -> list[ErrorGroup]:
    """Group ERROR-level log entries by normalized message pattern.

    Args:
        entries: List of raw log entries from YC Logging API.
        top_n: Return top N most frequent error groups.

    Returns:
        Sorted list of ErrorGroup (most frequent first).
    """
    error_messages: list[str] = []
    entry_map: dict[str, dict] = {}

    for entry in entries:
        level = _get_level(entry)
        if level not in ('ERROR', 'FATAL', 'CRITICAL'):
            continue

        message = _get_message(entry)
        if not message:
            continue

        pattern = _normalize_error(message)

        # Keep first occurrence of each pattern as sample
        if pattern not in entry_map:
            entry_map[pattern] = entry

        error_messages.append(pattern)

    counts = Counter(error_messages)
    result = [
        ErrorGroup(pattern=pattern, sample_entry=entry_map[pattern], count=count)
        for pattern, count in counts.most_common(top_n)
    ]

    return result


def summarize_errors(entries: list[dict], top_n: int = 10) -> str:
    """Format error summary as readable text."""
    groups = group_errors(entries, top_n=top_n)

    if not groups:
        return 'No errors found in the specified period.'

    total_errors = sum(g.count for g in groups)
    lines = [
        f'Found {total_errors} ERROR-level entries ({len(groups)} unique patterns).',
        '',
    ]

    for i, group in enumerate(groups, 1):
        sample_msg = _get_message(group.sample_entry)[:200]
        lines.append(f'{i}. [{group.count}x] {group.pattern[:120]}')
        lines.append(f'   Sample: {sample_msg}')

        if group.sample_request_id:
            lines.append(f'   Request ID: {group.sample_request_id}')

        lines.append('')

    return '\n'.join(lines)
