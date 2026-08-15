"""YC Logging gRPC client via yandexcloud SDK.

Uses YC_LOG_INSPECTOR_SA_JSON environment variable for authentication.
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from google.protobuf.json_format import MessageToDict
from google.protobuf.timestamp_pb2 import Timestamp  # type: ignore[attr-defined]
from yandex.cloud.logging.v1.log_entry_pb2 import LogLevel
from yandex.cloud.logging.v1.log_group_service_pb2 import ListLogGroupsRequest
from yandex.cloud.logging.v1.log_group_service_pb2_grpc import LogGroupServiceStub
from yandex.cloud.logging.v1.log_reading_service_pb2 import Criteria, ReadRequest
from yandex.cloud.logging.v1.log_reading_service_pb2_grpc import LogReadingServiceStub
from yandexcloud import SDK

logger = logging.getLogger(__name__)

_ENV_VAR = 'YC_LOG_INSPECTOR_SA_JSON'

# Map REST-style level names to protobuf enums
_LEVEL_TO_PROTO: dict[str, int] = {
    'TRACE': LogLevel.TRACE,
    'DEBUG': LogLevel.DEBUG,
    'INFO': LogLevel.INFO,
    'WARN': LogLevel.WARN,
    'WARNING': LogLevel.WARN,
    'ERROR': LogLevel.ERROR,
    'CRITICAL': LogLevel.FATAL,
    'FATAL': LogLevel.FATAL,
}

# Below this window size filtered reads stop bisecting and accept a full page.
_MIN_WINDOW = timedelta(minutes=1)

# Pause between gRPC Read requests to stay under YC's ~5 rps limit.
_THROTTLE_SECONDS = 0.3

# YC caps Criteria.page_size at 1000.
_MAX_PAGE_SIZE = 1000


class AuthError(RuntimeError):
    """Authentication-related errors."""


@dataclass
class LogGroup:
    id: str
    name: str
    folder_id: str


def _make_sdk() -> SDK:
    """Create and return an authenticated yandexcloud SDK instance."""
    sa_json = os.environ.get(_ENV_VAR)
    if not sa_json:
        raise AuthError(
            f'{_ENV_VAR} environment variable is not set. '
            'Create a service account key via YC CLI:\n'
            '  yc iam key create --service-account-name <name> --output key.json\n'
            f'Then set {_ENV_VAR} to the contents of key.json'
        )
    return SDK(service_account_key=json.loads(sa_json))


def _entry_to_dict(entry: Any) -> dict[str, Any]:
    """Convert a protobuf LogEntry to a plain dict compatible with analytics."""
    d: dict[str, Any] = {
        'uid': entry.uid,
        'level': LogLevel.Level.Name(entry.level),
        'message': entry.message,
        'timestamp': entry.timestamp.ToDatetime().isoformat(),
        'stream_name': entry.stream_name,
    }
    if entry.HasField('json_payload') and entry.json_payload:
        d['json_payload'] = MessageToDict(entry.json_payload)
    return d


def _dedupe_by_uid(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicate entries by 'uid', keeping the first occurrence."""
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for entry in entries:
        uid = entry.get('uid')
        if uid and uid in seen:
            continue
        if uid:
            seen.add(uid)
        deduped.append(entry)
    return deduped


class YCLoggingClient:
    """YC Logging gRPC client using yandexcloud SDK.

    Uses YC_LOG_INSPECTOR_SA_JSON for service account auth.
    """

    def __init__(self) -> None:
        self._sdk = _make_sdk()
        self._log_group_stub = self._sdk.client(LogGroupServiceStub)
        self._log_reading_stub = self._sdk.client(LogReadingServiceStub)

    # ── Log Groups ───────────────────────────────────────────────────

    def list_log_groups(self, folder_id: str) -> list[LogGroup]:
        """List available log groups in a YC folder."""
        request = ListLogGroupsRequest(folder_id=folder_id)
        response = self._log_group_stub.List(request)
        return [LogGroup(id=g.id, name=g.name, folder_id=g.folder_id) for g in response.groups]

    # ── Read Logs ────────────────────────────────────────────────────

    def read_logs(
        self,
        log_group_id: str,
        *,
        levels: list[str] | None = None,
        filter_str: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """Read a single page of log entries.

        Returns dict with 'entries' and optional 'next_page_token'.
        """
        criteria = Criteria(log_group_id=log_group_id, page_size=page_size)

        if levels:
            proto_levels = []
            for lvl in levels:
                enum_val = _LEVEL_TO_PROTO.get(lvl.upper())
                if enum_val is not None:
                    proto_levels.append(enum_val)
            criteria.levels.extend(proto_levels)  # type: ignore[arg-type]

        if filter_str:
            criteria.filter = filter_str

        if from_time:
            ts = Timestamp()
            ts.FromDatetime(from_time)
            criteria.since.CopyFrom(ts)

        if to_time:
            ts = Timestamp()
            ts.FromDatetime(to_time)
            criteria.until.CopyFrom(ts)

        if page_token:
            # NB: page_token and criteria are a protobuf `oneof` — they are
            # mutually exclusive. For subsequent pages only the token is sent.
            request = ReadRequest(page_token=page_token)
        else:
            request = ReadRequest(criteria=criteria)

        response = self._log_reading_stub.Read(request)

        return {
            'entries': [_entry_to_dict(e) for e in response.entries],
            'next_page_token': response.next_page_token or None,
        }

    def read_all_logs(
        self,
        log_group_id: str,
        *,
        levels: list[str] | None = None,
        filter_str: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        max_pages: int = 500,
        slice_hours: float = 1.0,
        retries: int = 3,
        page_size: int = 1000,
        throttle_seconds: float = _THROTTLE_SECONDS,
    ) -> list[dict[str, Any]]:
        """Read all matching log entries.

        Filtered reads (``levels`` and/or ``filter_str``) cannot rely on
        page_token pagination: after a criteria that combines levels and
        ``until``, a page_token request comes back **empty**, silently
        dropping matches. So filtered reads never paginate — one criteria
        request (since+until+levels) per window. If the page comes back full
        (``len(entries) == page_size``) the window may hold more matches, so
        it is bisected in half recursively (down to ``_MIN_WINDOW``) and each
        half is read the same way. The full page's own entries are kept too;
        results are deduplicated by ``uid`` (bisected halves may overlap at
        the boundary).

        Unfiltered reads keep page_token pagination (tokens work there):
        ``until`` is NOT sent and ``to_time`` is applied client-side.

        Read requests are throttled (``throttle_seconds``) to respect YC's
        ~5 requests/second limit; transient gRPC errors are retried.

        Args:
            log_group_id: YC log group id.
            levels: log levels to filter by (e.g. ['ERROR']).
            filter_str: custom YC filter expression.
            from_time / to_time: window bounds (UTC).
            max_pages: max pages per chunk (unfiltered path only).
            slice_hours: window slice size in hours. Set to 0 to disable
                slicing — filtered reads then rely on bisection.
            retries: how many times to retry a failed Read call.
            page_size: page size for Read requests (max 1000).
            throttle_seconds: pause between Read requests (~0.3-0.5s).
        """
        if from_time is None:
            from_time = datetime.now(timezone.utc) - timedelta(hours=1)
        if to_time is None:
            to_time = datetime.now(timezone.utc)

        page_size = max(1, min(page_size, _MAX_PAGE_SIZE))

        entries: list[dict[str, Any]] = []
        if slice_hours and slice_hours > 0:
            t = from_time
            while t < to_time:
                chunk_to = min(t + timedelta(hours=slice_hours), to_time)
                entries.extend(
                    self._read_window(
                        log_group_id,
                        levels=levels,
                        filter_str=filter_str,
                        from_time=t,
                        to_time=chunk_to,
                        max_pages=max_pages,
                        retries=retries,
                        page_size=page_size,
                        throttle_seconds=throttle_seconds,
                    )
                )
                t = chunk_to
        else:
            entries.extend(
                self._read_window(
                    log_group_id,
                    levels=levels,
                    filter_str=filter_str,
                    from_time=from_time,
                    to_time=to_time,
                    max_pages=max_pages,
                    retries=retries,
                    page_size=page_size,
                    throttle_seconds=throttle_seconds,
                )
            )

        return _dedupe_by_uid(entries)

    def _read_window(
        self,
        log_group_id: str,
        *,
        levels: list[str] | None,
        filter_str: str | None,
        from_time: datetime,
        to_time: datetime,
        max_pages: int,
        retries: int,
        page_size: int,
        throttle_seconds: float,
    ) -> list[dict[str, Any]]:
        """Read one time slice, picking the strategy by whether a filter is set."""
        if levels or filter_str:
            return self._read_filtered_window(
                log_group_id,
                levels=levels,
                filter_str=filter_str,
                from_time=from_time,
                to_time=to_time,
                page_size=page_size,
                retries=retries,
                throttle_seconds=throttle_seconds,
            )
        return self._read_chunk(
            log_group_id,
            levels=levels,
            filter_str=filter_str,
            from_time=from_time,
            to_time=to_time,
            max_pages=max_pages,
            retries=retries,
            page_size=page_size,
            throttle_seconds=throttle_seconds,
        )

    def _read_filtered_window(
        self,
        log_group_id: str,
        *,
        levels: list[str] | None,
        filter_str: str | None,
        from_time: datetime,
        to_time: datetime,
        page_size: int,
        retries: int,
        throttle_seconds: float,
    ) -> list[dict[str, Any]]:
        """Read a filtered window with one criteria request (since+until+levels).

        A full page (``len(entries) == page_size``) means the window may hold
        more matches than fit in one page — bisect the window and read each
        half recursively until every half fits in a page or ``_MIN_WINDOW``
        is reached. Overlaps between halves are removed by uid dedup in
        ``read_all_logs``.
        """
        page = self._read_page(
            log_group_id,
            levels=levels,
            filter_str=filter_str,
            from_time=from_time,
            to_time=to_time,
            page_size=page_size,
            page_token=None,
            retries=retries,
            throttle_seconds=throttle_seconds,
        )
        entries = page.get('entries', [])

        if len(entries) < page_size or to_time - from_time <= _MIN_WINDOW:
            return entries

        mid = from_time + (to_time - from_time) / 2
        left = self._read_filtered_window(
            log_group_id,
            levels=levels,
            filter_str=filter_str,
            from_time=from_time,
            to_time=mid,
            page_size=page_size,
            retries=retries,
            throttle_seconds=throttle_seconds,
        )
        right = self._read_filtered_window(
            log_group_id,
            levels=levels,
            filter_str=filter_str,
            from_time=mid,
            to_time=to_time,
            page_size=page_size,
            retries=retries,
            throttle_seconds=throttle_seconds,
        )
        return entries + left + right

    def _read_chunk(
        self,
        log_group_id: str,
        *,
        levels: list[str] | None,
        filter_str: str | None,
        from_time: datetime | None,
        to_time: datetime | None,
        max_pages: int,
        retries: int,
        page_size: int,
        throttle_seconds: float,
    ) -> list[dict[str, Any]]:
        """Read one time slice via page_token pagination (unfiltered path).

        ``until`` is NOT sent to YC (it breaks page tokens); ``to_time`` is
        filtered on the client side instead.
        """
        entries: list[dict[str, Any]] = []
        page_token: str | None = None
        pages = 0

        while pages < max_pages:
            result = self._read_page(
                log_group_id,
                levels=levels,
                filter_str=filter_str,
                from_time=from_time,
                to_time=None,  # NB: until breaks pagination — filter below
                page_size=page_size,
                page_token=page_token,
                retries=retries,
                throttle_seconds=throttle_seconds,
            )
            batch = result.get('entries', [])
            if to_time is not None:
                batch = [e for e in batch if e.get('timestamp', '') < to_time.isoformat()]
            entries.extend(batch)
            pages += 1

            page_token = result.get('next_page_token')
            if not page_token or not batch:
                break

        return entries

    def _read_page(
        self,
        log_group_id: str,
        *,
        levels: list[str] | None,
        filter_str: str | None,
        from_time: datetime | None,
        to_time: datetime | None,
        page_size: int,
        page_token: str | None,
        retries: int,
        throttle_seconds: float,
    ) -> dict[str, Any]:
        """Single Read call with throttling and per-call retries.

        Returns ``{'entries': [...], 'next_page_token': ...}`` or an empty
        page dict if all retries are exhausted.
        """
        attempt = 0
        while True:
            try:
                if throttle_seconds > 0:
                    time.sleep(throttle_seconds)
                return self.read_logs(
                    log_group_id,
                    levels=levels,
                    filter_str=filter_str,
                    from_time=from_time,
                    to_time=to_time,
                    page_size=page_size,
                    page_token=page_token,
                )
            except Exception as exc:
                attempt += 1
                if attempt >= retries:
                    logger.warning(
                        'read_logs failed after %d attempts (%s); window from=%s to=%s',
                        attempt,
                        exc,
                        from_time,
                        to_time,
                    )
                    return {'entries': [], 'next_page_token': None}
                time.sleep(1 * attempt)

    def close(self) -> None:
        """No-op for compatibility; gRPC channels managed by SDK."""
