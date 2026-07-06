"""YC Logging REST API client.

Uses YC_SERVICE_ACCOUNT_JSON environment variable for authentication.
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt

logger = logging.getLogger(__name__)

YC_IAM_TOKEN_URL = 'https://iam.api.cloud.yandex.net/iam/v1/tokens'
YC_LOGGING_BASE_URL = 'https://api.logging.yandexcloud.net/logging/v1'


class AuthError(RuntimeError):
    """Authentication-related errors."""


class IamTokenAuth:
    """Provides an IAM token from the YC_SERVICE_ACCOUNT_JSON environment variable.

    Exchanges the service account key for an IAM token via the YC IAM API.
    Caches the token and handles refresh on expiry.
    """

    def __init__(self) -> None:
        self._token: str | None = None
        self._expiry: datetime | None = None

    def get_token(self) -> str:
        """Return a valid IAM token, exchanging SA key if needed."""
        if self._token and self._expiry and datetime.now(timezone.utc) < self._expiry:
            return self._token

        sa_json = os.environ.get('YC_SERVICE_ACCOUNT_JSON')
        if not sa_json:
            raise AuthError(
                'YC_SERVICE_ACCOUNT_JSON environment variable is not set. '
                'Create a service account key via YC CLI:\n'
                '  yc iam key create --service-account-name <name> --output key.json\n'
                'Then set YC_SERVICE_ACCOUNT_JSON to the contents of key.json'
            )

        self._token = self._exchange_sa_key(sa_json)
        # IAM tokens are valid for 12h, refresh after 11h
        self._expiry = datetime.now(timezone.utc) + timedelta(hours=11)
        return self._token

    @staticmethod
    def _make_jwt(sa_key: dict) -> str:
        """Create a signed JWT using a Yandex Cloud service account key."""
        now = int(time.time())
        payload = {
            'aud': YC_IAM_TOKEN_URL,
            'iss': sa_key['service_account_id'],
            'iat': now,
            'exp': now + 3600,
        }
        headers = {'kid': sa_key['id'], 'typ': 'JWT'}
        return jwt.encode(payload, sa_key['private_key'], algorithm='PS256', headers=headers)

    def _exchange_sa_key(self, sa_json_str: str) -> str:
        """Exchange service account key JSON for an IAM token."""
        sa_key = json.loads(sa_json_str)
        jwt_token = self._make_jwt(sa_key)
        resp = httpx.post(YC_IAM_TOKEN_URL, json={'jwt': jwt_token}, timeout=10)
        resp.raise_for_status()
        return resp.json()['iamToken']

    def invalidate(self) -> None:
        """Force token refresh on next call."""
        self._token = None
        self._expiry = None


@dataclass
class LogGroup:
    id: str
    name: str
    folder_id: str


class YCLoggingClient:
    """YC Logging REST API client.

    Uses IamTokenAuth for authentication via the YC_SERVICE_ACCOUNT_JSON env var.
    """

    def __init__(self, auth: IamTokenAuth | None = None) -> None:
        self._auth = auth or IamTokenAuth()
        self._http = httpx.Client(timeout=30.0)

    # ── Internal HTTP ───────────────────────────────────────────────

    def _ensure_headers(self) -> dict[str, str]:
        """Return auth headers, fetching/refreshing token as needed."""
        token = self._auth.get_token()
        return {'Authorization': f'Bearer {token}'}

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        """Make an authenticated request with automatic token refresh on 401."""
        headers = self._ensure_headers()
        headers.update(kwargs.pop('headers', {}))

        resp = self._http.request(method, url, headers=headers, **kwargs)

        if resp.status_code == 401:
            # Token expired, force refresh and retry once
            self._auth.invalidate()
            headers = self._ensure_headers()
            headers.update(kwargs.pop('headers', {}))
            resp = self._http.request(method, url, headers=headers, **kwargs)

        resp.raise_for_status()
        return resp.json()

    # ── API Methods ─────────────────────────────────────────────────

    def list_log_groups(self, folder_id: str) -> list[LogGroup]:
        """List available log groups in a YC folder."""
        data = self._request(
            'GET',
            f'{YC_LOGGING_BASE_URL}/logGroups',
            params={'folderId': folder_id},
        )
        return [
            LogGroup(
                id=g['id'],
                name=g.get('name', ''),
                folder_id=g.get('folderId', ''),
            )
            for g in data.get('groups', [])
        ]

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
        body: dict[str, Any] = {'page_size': page_size}

        criteria: dict[str, Any] = {}
        if levels:
            criteria['levels'] = levels
        if filter_str:
            criteria['filter'] = filter_str
        if criteria:
            body['criteria'] = criteria

        if from_time:
            body['from'] = from_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        if to_time:
            body['to'] = to_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        if page_token:
            body['page_token'] = page_token

        return self._request(
            'POST',
            f'{YC_LOGGING_BASE_URL}/logGroupId/{log_group_id}/entries:read',
            json=body,
        )

    def read_all_logs(
        self,
        log_group_id: str,
        *,
        levels: list[str] | None = None,
        filter_str: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        max_pages: int = 50,
    ) -> list[dict[str, Any]]:
        """Read all matching log entries (auto-paginated)."""
        entries: list[dict[str, Any]] = []
        page_token: str | None = None
        pages = 0

        while pages < max_pages:
            result = self.read_logs(
                log_group_id,
                levels=levels,
                filter_str=filter_str,
                from_time=from_time,
                to_time=to_time,
                page_token=page_token,
            )
            batch = result.get('entries', [])
            entries.extend(batch)
            pages += 1

            page_token = result.get('next_page_token')
            if not page_token or not batch:
                break

        return entries

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()
