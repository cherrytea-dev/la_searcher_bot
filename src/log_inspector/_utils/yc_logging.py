"""Yandex Cloud Logging REST API client."""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Max page size allowed by Yandex Cloud Logging API
MAX_PAGE_SIZE = 1000

# Metadata service URL for IAM token retrieval (inside Yandex Cloud Functions)
METADATA_URL = 'http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token'

# Yandex Cloud Logging API base URL
API_BASE = 'https://logging.api.cloud.yandex.net/logging/v1'


class YcLoggingError(Exception):
    """Base exception for YC Logging API errors."""


class AuthError(YcLoggingError):
    """Authentication-related errors."""


class YcLoggingClient:
    """Client for Yandex Cloud Logging REST API.

    Authentication priority:
    1. YC_IAM_TOKEN env var (explicit IAM token)
    2. YC_SERVICE_ACCOUNT_JSON env var (service account key, generates IAM token)
    3. Metadata service (when running inside Yandex Cloud Functions)
    """

    def __init__(self, folder_id: str | None = None) -> None:
        self._folder_id = folder_id or os.environ.get('YC_FOLDER_ID', '')
        self._iam_token: str | None = None
        self._token_expiry: datetime | None = None
        self._http = httpx.Client(timeout=30.0)

    # ── Authentication ──────────────────────────────────────────────

    def _get_iam_token(self) -> str:
        """Obtain IAM token using the best available method."""
        # 1. Explicit IAM token
        token = os.environ.get('YC_IAM_TOKEN')
        if token:
            return token

        # 2. Service account key (JSON)
        sa_json = os.environ.get('YC_SERVICE_ACCOUNT_JSON')
        if sa_json:
            return self._exchange_sa_key(sa_json)

        # 3. Metadata service (inside Yandex Cloud)
        if self._is_in_yc():
            return self._get_token_from_metadata()

        raise AuthError(
            'No Yandex Cloud credentials found. '
            'Set YC_IAM_TOKEN or YC_SERVICE_ACCOUNT_JSON env var, '
            'or run inside Yandex Cloud Functions.'
        )

    @staticmethod
    def _is_in_yc() -> bool:
        return bool(os.environ.get('YC_FUNCTION_ID') or os.environ.get('REMOTE_EXECUTION'))

    def _get_token_from_metadata(self) -> str:
        try:
            resp = self._http.get(
                METADATA_URL,
                headers={'Metadata-Flavor': 'Google'},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            return data['access_token']
        except Exception as exc:
            raise AuthError(f'Failed to get IAM token from metadata: {exc}') from exc

    def _exchange_sa_key(self, sa_json: str) -> str:
        """Exchange a service account key for an IAM token.

        Uses the standard Yandex Cloud IAM JWT authentication flow.
        For simplicity, this reads the API key directly.
        """
        try:
            key_data = json.loads(sa_json)
            api_key = key_data.get('api_key') or key_data.get('service_account_id', '')
            if not api_key:
                raise AuthError('Service account JSON must contain "api_key" or "service_account_id"')
            return self._get_iam_token_from_api_key(api_key)
        except json.JSONDecodeError:
            # Maybe it's just an API key, try directly
            return self._get_iam_token_from_api_key(sa_json)

    def _get_iam_token_from_api_key(self, api_key: str) -> str:
        """Convert Yandex Cloud API key to an IAM token."""
        resp = self._http.post(
            'https://iam.api.cloud.yandex.net/iam/v1/tokens',
            json={'yandexPassportOauthToken': api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        return data['iamToken']

    def _ensure_token(self) -> str:
        """Get a valid IAM token, refreshing if needed."""
        if self._iam_token and self._token_expiry and datetime.now(timezone.utc) < self._token_expiry:
            return self._iam_token

        self._iam_token = self._get_iam_token()
        # IAM tokens are valid for 12h, refresh after 11h
        self._token_expiry = datetime.now(timezone.utc) + timedelta(hours=11)
        return self._iam_token

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        """Make an authenticated request to the YC Logging API."""
        token = self._ensure_token()
        url = f'{API_BASE}/{path.lstrip("/")}'

        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f'Bearer {token}'
        headers['Content-Type'] = 'application/json'

        resp = self._http.request(method, url, headers=headers, **kwargs)

        if resp.status_code == 401:
            # Token expired, force refresh and retry once
            self._iam_token = None
            self._token_expiry = None
            token = self._ensure_token()
            headers['Authorization'] = f'Bearer {token}'
            resp = self._http.request(method, url, headers=headers, **kwargs)

        resp.raise_for_status()
        return resp.json()

    # ── API Methods ─────────────────────────────────────────────────

    def list_log_groups(self) -> list[dict]:
        """List all available log groups in the folder."""
        path = f'logGroups?folderId={self._folder_id}'
        data = self._request('GET', path)
        return data.get('groups', [])

    def read_logs(
        self,
        group_id: str,
        *,
        level: str = 'ERROR',
        since: timedelta | None = None,
        until: datetime | None = None,
        filter_str: str | None = None,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict:
        """Read log entries from a log group.

        Args:
            group_id: Log group ID.
            level: Minimum log level (ERROR, WARN, INFO, DEBUG, TRACE).
            since: Time range start (relative to now).
            until: Time range end (absolute).
            filter_str: Additional YC Logging filter string.
            page_size: Results per page (max 1000).
            page_token: Pagination token for next page.

        Returns:
            API response dict with 'entries' and optional 'nextPageToken'.
        """
        until_time = until or datetime.now(timezone.utc)
        since_time = (until_time - since) if since else (until_time - timedelta(days=1))

        filters = [f'level={level}']
        if filter_str:
            filters.append(f'({filter_str})')
        full_filter = ' AND '.join(filters)

        body: dict[str, Any] = {
            'pageSize': min(page_size, MAX_PAGE_SIZE),
            'filter': full_filter,
            'sinceTime': since_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'untilTime': until_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        }

        if page_token:
            body['pageToken'] = page_token

        return self._request('POST', f'logGroups/{group_id}:read', json=body)

    def read_all_logs(
        self,
        group_id: str,
        *,
        level: str = 'ERROR',
        since: timedelta | None = None,
        until: datetime | None = None,
        filter_str: str | None = None,
        max_entries: int = 5000,
    ) -> list[dict]:
        """Read all log entries across paginated responses.

        Args:
            Same as read_logs().
            max_entries: Maximum entries to collect across all pages.

        Returns:
            Combined list of log entries.
        """
        entries: list[dict] = []
        page_token: str | None = None

        while len(entries) < max_entries:
            remaining = max_entries - len(entries)
            page_size = min(MAX_PAGE_SIZE, remaining)

            data = self.read_logs(
                group_id,
                level=level,
                since=since,
                until=until,
                filter_str=filter_str,
                page_size=page_size,
                page_token=page_token,
            )

            page_entries = data.get('entries', [])
            entries.extend(page_entries)

            next_token = data.get('nextPageToken')
            if not next_token or not page_entries:
                break
            page_token = next_token

        return entries

    def get_logs_by_request_id(
        self,
        group_id: str,
        request_id: str,
        *,
        since: timedelta | None = None,
        max_entries: int = 500,
    ) -> list[dict]:
        """Get all log entries for a specific request_id."""
        return self.read_all_logs(
            group_id,
            level='TRACE',
            since=since or timedelta(days=1),
            filter_str=f'json_payload.request_id="{request_id}"',
            max_entries=max_entries,
        )

    def close(self) -> None:
        self._http.close()
