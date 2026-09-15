"""Log volume aggregation — which service writes how much, and where the bytes go.

YC Logging is billed (and queried) by ingested volume, and the cloud-function
logs are far from uniform: a couple of services own most of the bytes. This
module answers "how much per day, per service, and which records are the
fattest" without keeping the whole window in memory — entries are folded into
per-stream counters as they are read, so a 24h window over ~1.6M records is
fine on a small box.

Size caveat: :func:`entry_size` measures the JSON form of an entry as returned
by the Logging API (after ``MessageToDict``). That is a stable *proxy* for
stored volume, not YC's exact billing number — it counts the payload we
receive, not the platform's envelope/metadata overhead.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

UNKNOWN_STREAM = '<unknown>'

#: How much of a message goes into the "top messages" table.
MESSAGE_PREVIEW_WIDTH = 120


def _as_text(value: Any) -> str | None:
    """Return ``value`` as text; repeated protobuf fields arrive as lists."""
    if value is None:
        return None
    if isinstance(value, list):
        return _as_text(value[0]) if value else None
    return str(value)


def _json_payload(entry: dict[str, Any]) -> dict[str, Any]:
    payload = entry.get('json_payload')
    return payload if isinstance(payload, dict) else {}


def stream_of(entry: dict[str, Any]) -> str:
    """Name of the service that wrote the entry.

    ``stream_name`` from the JSON payload wins (it comes from the repo's
    ``setup_logging(__package__)``), then the platform's own ``stream_name``
    field, then :data:`UNKNOWN_STREAM`.
    """
    payload = _json_payload(entry)
    name = _as_text(payload.get('stream_name') or payload.get('streamName'))
    return name or _as_text(entry.get('stream_name')) or UNKNOWN_STREAM


def message_of(entry: dict[str, Any]) -> str:
    """Log message of the entry (JSON payload first, platform field second)."""
    payload = _json_payload(entry)
    text = _as_text(payload.get('message') or payload.get('msg'))
    return text if text is not None else (_as_text(entry.get('message')) or '')


def entry_size(entry: dict[str, Any]) -> int:
    """Approximate stored size of the entry, in UTF-8 bytes."""
    return len(json.dumps(entry, ensure_ascii=False, default=str).encode('utf-8'))


def preview(message: str, width: int = MESSAGE_PREVIEW_WIDTH) -> str:
    """Collapse whitespace and truncate a message for table output."""
    return ' '.join(message.split())[:width]


@dataclass
class StreamStats:
    """Per-service totals."""

    name: str
    count: int = 0
    size: int = 0
    levels: Counter[str] = field(default_factory=Counter)
    messages: Counter[str] = field(default_factory=Counter)

    @property
    def bytes_per_record(self) -> float:
        """Average record size for this service."""
        return self.size / self.count if self.count else 0.0


@dataclass
class VolumeReport:
    """Aggregated volume for a read window, plus extrapolation to a full day."""

    hours_read: float
    window_hours: float
    streams: list[StreamStats]
    biggest: list[tuple[int, str, str]] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        """Total records across all services."""
        return sum(stream.count for stream in self.streams)

    @property
    def total_size(self) -> int:
        """Total bytes across all services."""
        return sum(stream.size for stream in self.streams)

    @property
    def scale(self) -> float:
        """Multiplier that turns the read window into ``window_hours``.

        Sampling fewer hours than the window (``--sample-every``) is scaled up
        here, so the per-day columns stay comparable.
        """
        return self.window_hours / self.hours_read if self.hours_read else 0.0

    def share(self, stream: StreamStats) -> float:
        """Share of the read bytes owned by ``stream``, in percent."""
        total = self.total_size
        return stream.size / total * 100 if total else 0.0

    @property
    def per_day_size(self) -> float:
        """Extrapolated bytes per day."""
        return self.total_size * self.scale

    @property
    def per_day_count(self) -> float:
        """Extrapolated records per day."""
        return self.total_count * self.scale

    def to_dict(self, top_messages: int = 3, top_biggest: int = 5) -> dict[str, Any]:
        """Machine-readable form (for ``--json``)."""
        return {
            'hours_read': self.hours_read,
            'window_hours': self.window_hours,
            'scale': self.scale,
            'total_records': self.total_count,
            'total_bytes': self.total_size,
            'bytes_per_day': self.per_day_size,
            'records_per_day': self.per_day_count,
            'streams': [
                {
                    'name': stream.name,
                    'records': stream.count,
                    'bytes': stream.size,
                    'share_percent': self.share(stream),
                    'bytes_per_record': stream.bytes_per_record,
                    'bytes_per_day': stream.size * self.scale,
                    'records_per_day': stream.count * self.scale,
                    'levels': dict(stream.levels),
                    'top_messages': [
                        {'count': count, 'message': message}
                        for message, count in stream.messages.most_common(top_messages)
                    ],
                }
                for stream in self.streams
            ],
            'biggest_records': [
                {'bytes': size, 'stream': stream, 'message': message}
                for size, stream, message in self.biggest[:top_biggest]
            ],
        }

    def render(self, top_messages: int = 3, top_biggest: int = 5, top_streams: int = 6) -> str:
        """Human-readable report: table, levels, top messages, fattest records."""
        scale = self.scale
        name_width = max([len(stream.name) for stream in self.streams] + [len('TOTAL')]) + 2
        header = (
            f'{"Service":<{name_width}}{"records":>13}{"MB":>10}{"share,%":>9}{"B/rec":>8}{"MB/day":>10}{"rec/day":>13}'
        )
        lines = ['', header, '-' * len(header)]
        for stream in self.streams:
            lines.append(
                f'{stream.name:<{name_width}}{_n(stream.count):>13}{stream.size / 1e6:>10.1f}{self.share(stream):>9.1f}'
                f'{stream.bytes_per_record:>8.0f}{stream.size * scale / 1e6:>10.1f}'
                f'{_n(round(stream.count * scale)):>13}',
            )
        lines.append('-' * len(header))
        lines.append(
            f'{"TOTAL":<{name_width}}{_n(self.total_count):>13}{self.total_size / 1e6:>10.1f}{100:>9.1f}'
            f'{self.total_size / max(self.total_count, 1):>8.0f}{self.per_day_size / 1e6:>10.1f}'
            f'{_n(round(self.per_day_count)):>13}',
        )
        lines.append('')
        lines.append(
            f'Hours read: {self.hours_read:g} (window {self.window_hours:g}h, scale x{scale:.2f}). '
            f'Per day: {self.per_day_size / 1e9:.2f} GB, {_n(round(self.per_day_count))} records.',
        )

        if not self.total_count:
            return '\n'.join(lines)

        lines.append('')
        lines.append('Levels per service:')
        for stream in self.streams[:top_streams]:
            levels = ', '.join(f'{level}={_n(count)}' for level, count in stream.levels.most_common())
            lines.append(f'  {stream.name:<{name_width}}{levels}')

        lines.append('')
        lines.append('Top messages per service:')
        for stream in self.streams[:top_streams]:
            lines.append(f'  {stream.name} — {_n(stream.count)} records, {stream.size / 1e6:.1f} MB')
            for message, count in stream.messages.most_common(top_messages):
                lines.append(f'      {_n(count):>10} × {message[:100]}')

        if self.biggest:
            lines.append('')
            lines.append('Fattest records:')
            for size, stream, message in self.biggest[:top_biggest]:
                lines.append(f'  {_n(size):>10} B  [{stream}] {message[:90]}')

        return '\n'.join(lines)


class VolumeAggregator:
    """Fold log entries into per-service counters, slice by slice.

    Memory stays flat regardless of how many entries are read: only counters,
    one preview string per distinct message, and the ``top_biggest`` largest
    records are kept.
    """

    def __init__(self, top_biggest: int = 10) -> None:
        self._streams: dict[str, StreamStats] = {}
        self._biggest: list[tuple[int, str, str]] = []
        self._top_biggest = top_biggest
        self.hours_read = 0

    def add_slice(self, entries: list[dict[str, Any]]) -> int:
        """Add one read time slice; counts as one read hour.

        Returns the total size of the slice, so callers can report progress
        without measuring the same entries twice.
        """
        slice_size = 0
        for entry in entries:
            stream_name = stream_of(entry)
            size = entry_size(entry)
            stream = self._streams.get(stream_name)
            if stream is None:
                stream = self._streams[stream_name] = StreamStats(name=stream_name)

            stream.count += 1
            stream.size += size
            slice_size += size
            stream.levels[str(entry.get('level') or '?')] += 1
            stream.messages[preview(message_of(entry))] += 1

            if self._top_biggest > 0:
                self._keep_biggest(size, stream_name, preview(message_of(entry)))

        self.hours_read += 1
        return slice_size

    def _keep_biggest(self, size: int, stream_name: str, message: str) -> None:
        self._biggest.append((size, stream_name, message))
        if len(self._biggest) > self._top_biggest * 4:
            self._biggest.sort(reverse=True)
            del self._biggest[self._top_biggest :]

    def report(self, window_hours: float) -> VolumeReport:
        """Freeze the counters into a report for the given window length."""
        streams = sorted(self._streams.values(), key=lambda stream: stream.size, reverse=True)
        biggest = sorted(self._biggest, reverse=True)[: self._top_biggest]
        return VolumeReport(
            hours_read=self.hours_read,
            window_hours=window_hours,
            streams=streams,
            biggest=biggest,
        )


def _n(value: float) -> str:
    """Group thousands with spaces (readable in a terminal)."""
    return f'{value:,.0f}'.replace(',', ' ')
