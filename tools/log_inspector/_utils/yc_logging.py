"""YC Logging REST API client.

Auth priority: YC_IAM_TOKEN → YC_LOG_INSPECTOR_SA_JSON → metadata service.
"""

import base64
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


YC_IAM_TOKEN_URL = 'https://iam.api.cloud.yandex.net/iam/v1/tokens'
YC_LOGGING_BASE_URL = 'https://api.logging.yandexcloud.net/logging/v1'
METADATA_TOKEN_URL = (
    'http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token'
)


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _make_jwt(sa_key: dict) -> str:
    """Create a signed JWT using a Yandex Cloud service account key."""
    private_key = serialization.load_pem_private_key(
        sa_key['private_key'].encode(), password=None
    )
    now = int(time.time())
    header = _base64url_encode(
        json.dumps({'alg': 'PS256', 'typ': 'JWT', 'kid': sa_key['id']}).encode()
    )
    payload = _base64url_encode(
        json.dumps(
            {
                'aud': YC_IAM_TOKEN_URL,
                'iss': sa_key['service_account_id'],
                'iat': now,
                'exp': now + 3600,
            }
        ).encode()
    )
    signing_input = f'{header}.{payload}'
    signature = private_key.sign(
        signing_input.encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return f'{signing_input}.{_base64url_encode(signature)}'


def _token_from_sa_json(sa_json_str: str) -> str:
    """Exchange service account key JSON for an IAM token."""
    sa_key = json.loads(sa_json_str)
    jwt_token = _make_jwt(sa_key)
    resp = httpx.post(YC_IAM_TOKEN_URL, json={'jwt': jwt_token}, timeout=10)
    resp.raise_for_status()
    return resp.json()['iamToken']


def _token_from_metadata() -> str | None:
    """Try to get IAM token from YC metadata service (inside VM/Function)."""
    try:
        resp = httpx.get(
            METADATA_TOKEN_URL,
            headers={'Metadata-Flavor': 'Google'},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()['access_token']
    except Exception:
        return None


def get_iam_token() -> str:
    """Resolve IAM token from available sources.

    Priority:
      1. YC_IAM_TOKEN env var (ready-to-use token)
      2. YC_LOG_INSPECTOR_SA_JSON env var (service account key JSON)
      3. YC metadata service (inside Yandex Cloud VMs/Functions)
    """
    # 1. Direct IAM token
    token = os.environ.get('YC_IAM_TOKEN')
    if token:
        return token

    # 2. Service account JSON key
    sa_json = os.environ.get('YC_LOG_INSPECTOR_SA_JSON')
    if sa_json:
        return _token_from_sa_json(sa_json)

    # 3. Metadata service
    token = _token_from_metadata()
    if token:
        return token

    raise RuntimeError(
        'No auth method available. Set YC_LOG_INSPECTOR_SA_JSON or YC_IAM_TOKEN.'
    )


@dataclass
class LogGroup:
    id: str
    name: str
    folder_id: str


class YCLoggingClient:
    """YC Logging REST API client."""

    def __init__(self, iam_token: str | None = None) -> None:
        self._token = iam_token or get_iam_token()
        self._client = httpx.Client(
            headers={'Authorization': f'Bearer {self._token}'}
        )

    def list_log_groups(self, folder_id: str) -> list[LogGroup]:
        """List available log groups in a YC folder."""
        resp = self._client.get(
            f'{YC_LOGGING_BASE_URL}/logGroups',
            params={'folderId': folder_id},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
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
    ) -> dict:
        """Read a single page of log entries.

        Returns dict with 'entries' and optional 'next_page_token'.
        """
        body: dict = {'page_size': page_size}

        criteria: dict = {}
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

        resp = self._client.post(
            f'{YC_LOGGING_BASE_URL}/logGroupId/{log_group_id}/entries:read',
            json=body,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()

    def read_all_logs(
        self,
        log_group_id: str,
        *,
        levels: list[str] | None = None,
        filter_str: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        max_pages: int = 50,
    ) -> list[dict]:
        """Read all matching log entries (auto-paginated)."""
        entries: list[dict] = []
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
