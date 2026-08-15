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
    ) -> list[dict[str, Any]]:
        """Read all matching log entries (auto-paginated, window-sliced).

        Observed YC Logging quirks (2026-08-15):

        * ``page_token`` and ``criteria`` are a protobuf ``oneof`` — sending
          both silently drops criteria. First request uses criteria, subsequent
          pages use the token alone.
        * ``until`` in criteria breaks pagination: the first page returns a
          token, but the next ``page_token`` request comes back **empty**.
          Workaround: never send ``until``; filter ``to_time`` client-side.
        * Large windows / heavy filters may raise gRPC UNAVAILABLE — split
          the window into ``slice_hours`` chunks and retry each chunk.
        * A read session caps at ~20k entries — slicing also works around this.

        Args:
            log_group_id: YC log group id.
            levels: log levels to filter by (e.g. ['ERROR']).
            filter_str: custom YC filter expression.
            from_time / to_time: window bounds (UTC). ``to_time`` is applied
                client-side because ``until`` breaks pagination.
            max_pages: max pages per chunk (page_size=100).
            slice_hours: window slice size in hours. Set to 0 to disable slicing.
            retries: how many times to retry a failed chunk read.
        """
        if from_time is None:
            from_time = datetime.now(timezone.utc) - timedelta(hours=1)
        if to_time is None:
            to_time = datetime.now(timezone.utc)

        if slice_hours and slice_hours > 0:
            entries: list[dict[str, Any]] = []
            t = from_time
            while t < to_time:
                chunk_to = min(t + timedelta(hours=slice_hours), to_time)
                entries.extend(
                    self._read_chunk(
                        log_group_id,
                        levels=levels,
                        filter_str=filter_str,
                        from_time=t,
                        to_time=chunk_to,
                        max_pages=max_pages,
                        retries=retries,
                    )
                )
                t = chunk_to
            return entries

        return self._read_chunk(
            log_group_id,
            levels=levels,
            filter_str=filter_str,
            from_time=from_time,
            to_time=to_time,
            max_pages=max_pages,
            retries=retries,
        )

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
    ) -> list[dict[str, Any]]:
        """Read one time slice with pagination and per-chunk retries.

        ``until`` is NOT sent to YC (it breaks page tokens); instead we filter
        ``to_time`` on the client side.
        """
        entries: list[dict[str, Any]] = []
        page_token: str | None = None
        pages = 0

        while pages < max_pages:
            attempt = 0
            while True:
                try:
                    result = self.read_logs(
                        log_group_id,
                        levels=levels,
                        filter_str=filter_str,
                        from_time=from_time,
                        to_time=None,  # NB: until breaks pagination — filter below
                        page_token=page_token,
                    )
                    break
                except Exception as exc:
                    attempt += 1
                    if attempt >= retries:
                        logger.warning(
                            'read_logs failed after %d attempts (%s); chunk from=%s to=%s',
                            attempt,
                            exc,
                            from_time,
                            to_time,
                        )
                        return entries
                    time.sleep(1 * attempt)

            batch = result.get('entries', [])
            if to_time is not None:
                batch = [e for e in batch if e.get('timestamp', '') < to_time.isoformat()]
            entries.extend(batch)
            pages += 1

            page_token = result.get('next_page_token')
            if not page_token or not batch:
                break

        return entries

    def close(self) -> None:
        """No-op for compatibility; gRPC channels managed by SDK."""
