"""Error pattern analysis and normalization."""

import re
from collections import Counter
from dataclasses import dataclass, field

# Patterns that normalize variable parts out of error messages.
# Order matters — apply UUID before generic hash/hex.
_NORMALIZE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'"), '<uuid>'),
    (re.compile(r'"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"'), '<uuid>'),
    (re.compile(r'(?<=\s)[0-9a-f]{32}(?=\s|$)'), '<hash>'),
    (re.compile(r'0x[0-9a-fA-F]+'), '<hex>'),
    (re.compile(r'\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'), '<timestamp>'),
    (re.compile(r'\b\d+\.\d+\.\d+\.\d+'), '<ip>'),
    (re.compile(r'/\d+/'), '/<id>/'),
    (re.compile(r'(?<=/)[0-9]+(?=/|$)'), '<num>'),
    (re.compile(r'telegram_id[=:]\s*\d+', re.IGNORECASE), 'telegram_id=<id>'),
    (re.compile(r'(?<=status[=:])\s*\d+', re.IGNORECASE), '<status>'),
    (re.compile(r'\b\d{10,}\b'), '<large_num>'),
]


def normalize_error(message: str) -> str:
    """Replace variable parts of an error message with stable placeholders."""
    result = message
    for pattern, replacement in _NORMALIZE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def extract_request_id(entry: dict) -> str | None:
    """Extract a request_id from a log entry.

    Checks json_payload first, then the message text.
    """
    json_payload = entry.get('json_payload', {})
    if isinstance(json_payload, dict):
        req_id = json_payload.get('request_id')
        if req_id:
            return str(req_id)

    message = entry.get('message', '')
    if not isinstance(message, str):
        return None

    match = re.search(r'request_id[=:]\s*([0-9a-f-]+)', message, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


@dataclass
class ErrorGroup:
    pattern: str
    count: int
    sample_message: str
    sample_request_ids: list[str] = field(default_factory=list)


def group_errors(
    entries: list[dict],
    top_n: int = 10,
    max_request_ids: int = 3,
) -> list[ErrorGroup]:
    """Group ERROR-level log entries by normalized pattern.

    Returns top-N groups sorted by occurrence count (descending).
    """
    error_entries = [e for e in entries if e.get('level') == 'ERROR']
    if not error_entries:
        return []

    pattern_counter: Counter[str] = Counter()
    pattern_samples: dict[str, str] = {}
    pattern_request_ids: dict[str, list[str]] = {}

    for entry in error_entries:
        message = entry.get('message', '') or ''
        pattern = normalize_error(message)
        pattern_counter[pattern] += 1

        if pattern not in pattern_samples:
            pattern_samples[pattern] = message

        req_id = extract_request_id(entry)
        if req_id and req_id not in pattern_request_ids.setdefault(pattern, []):
            if len(pattern_request_ids[pattern]) < max_request_ids:
                pattern_request_ids[pattern].append(req_id)

    return [
        ErrorGroup(
            pattern=pattern,
            count=count,
            sample_message=pattern_samples[pattern],
            sample_request_ids=pattern_request_ids.get(pattern, []),
        )
        for pattern, count in pattern_counter.most_common(top_n)
    ]
