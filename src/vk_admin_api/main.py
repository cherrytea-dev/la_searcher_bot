"""VK Admin Panel API — REST endpoints for managing user notification settings.

This function provides a JSON API for a web front-end (admin panel)
that replaces VK Bot's keyboard-based settings UI.

Authentication:
  - Telegram Login Widget (HMAC-SHA256 verification)
  - VK ID OAuth 2.0 with PKCE (browser flow)
  - VK Mini Apps (signed launch params — sign verification)

Endpoints:
  POST /api/v1/auth/tg       — Authenticate via Telegram Login Widget
  POST /api/v1/auth/vk       — Authenticate via VK (OAuth code, Mini Apps, or re-auth)
  GET  /api/v1/settings      — Full settings summary for a user
  GET  /api/v1/preferences   — List notification preferences
  POST /api/v1/preferences   — Toggle a notification preference
  DELETE /api/v1/preferences — Delete notification preferences
  GET  /api/v1/regions       — List all geo folders + user's subscriptions
  POST /api/v1/regions/toggle — Toggle a region subscription
  GET  /api/v1/coordinates   — Get user's home coordinates
  POST /api/v1/coordinates   — Save home coordinates
  DELETE /api/v1/coordinates — Delete home coordinates
  GET  /api/v1/radius        — Get notification radius
  POST /api/v1/radius        — Save notification radius
  DELETE /api/v1/radius      — Delete notification radius
  GET  /api/v1/age-preferences — Get age preferences
  POST /api/v1/age-preferences — Save an age period
  DELETE /api/v1/age-preferences — Delete an age period
  GET  /api/v1/topic-types   — Get topic type preferences
  POST /api/v1/topic-types   — Save a topic type
  DELETE /api/v1/topic-types — Delete a topic type
  GET  /api/v1/follow-mode   — Get search follow mode status
  POST /api/v1/follow-mode   — Toggle search follow mode
  GET  /api/v1/searches/active — Get active searches for user's regions
  GET  /api/v1/user/info     — Get basic user info (role, regions, forum)
"""

import base64
import hashlib
import hmac
import json
import logging
import os
from typing import Any

from _dependencies.commons import setup_logging
from _dependencies.misc import (
    RequestWrapper,
    ResponseWrapper,
    request_response_converter,
    verify_telegram_data,
)
from _dependencies.services.user_settings_service import (
    get_user_settings_service,
)

from . import handlers

setup_logging(__package__)

logger = logging.getLogger(__name__)

# ─── Constants ──────────────────────────────────────────────────────────

ALLOWED_ORIGINS = ['*']  # TODO: restrict in production

# VK OAuth 2.0 credentials (for code exchange)
VK_OAUTH_CLIENT_ID: str | None = os.getenv('VK_OAUTH_CLIENT_ID')
VK_OAUTH_CLIENT_SECRET: str | None = os.getenv('VK_OAUTH_CLIENT_SECRET')

# VK Mini App credentials (for sign verification)
VK_MINI_APP_SECRET: str | None = os.getenv('VK_MINI_APP_SECRET')

# ─── Response Helpers ───────────────────────────────────────────────────


def _ok_response(data: Any = None) -> ResponseWrapper:
    body = json.dumps({'ok': True, 'data': data}, ensure_ascii=False, default=str)
    return ResponseWrapper(body, 200, {'Content-Type': 'application/json'})


def _error_response(message: str, status: int = 400) -> ResponseWrapper:
    body = json.dumps({'ok': False, 'error': message}, ensure_ascii=False)
    return ResponseWrapper(body, status, {'Content-Type': 'application/json'})


def _cors_response() -> ResponseWrapper:
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Max-Age': '3600',
    }
    return ResponseWrapper('', 204, headers)


# ─── Authentication ─────────────────────────────────────────────────────


def _auth_tg(data: dict) -> int | None:
    """Authenticate via Telegram Login Widget data.

    Expects: {id, first_name, hash, auth_date, ...}
    Returns user_id if valid, None otherwise.
    """
    if not verify_telegram_data(data):
        return None
    user_id = data.get('id')
    if not isinstance(user_id, int):
        return None
    return user_id


def _verify_vk_mini_app_sign(launch_params: dict) -> bool:
    """Verify VK Mini Apps launch params signature.

    VK passes signed launch params in the URL when opening a Mini App:
    ?vk_user_id=123&vk_app_id=456&sign=abc...

    The sign is HMAC-SHA256 of sorted key=value pairs (excluding sign)
    using the VK Mini App secret key, then base64 encoded.

    See: https://dev.vk.com/en/mini-apps/development/launch-params
    """
    if not VK_MINI_APP_SECRET:
        logger.warning('VK_MINI_APP_SECRET not set, skipping sign verification')
        return False

    sign = launch_params.get('sign', '')
    if not sign:
        return False

    # Take all params except sign, sort alphabetically by key
    params_to_verify = {k: v for k, v in launch_params.items() if k != 'sign'}
    sorted_keys = sorted(params_to_verify.keys())

    # Build params string: key=value&key=value (alphabetical order)
    params_string = '&'.join(f'{k}={params_to_verify[k]}' for k in sorted_keys)

    # HMAC-SHA256 with VK Mini App secret
    expected_sign = base64.b64encode(
        hmac.new(
            VK_MINI_APP_SECRET.encode(),
            params_string.encode(),
            hashlib.sha256,
        ).digest()
    ).decode()

    return hmac.compare_digest(expected_sign, sign)


def _auth_vk(data: dict) -> int | None:
    """Authenticate via VK.

    Supports four modes:
    1. Re-auth by internal user_id: {user_id: int} — fast re-auth for subsequent requests
    2. VK Mini Apps (signed): {vk_user_id, sign, ...} — sign-verified launch params
    3. Mini Apps (legacy, unsigned): {vk_user_id: int} — direct VK platform user ID
    4. VK ID OAuth 2.0 with PKCE (browser):
       {code, code_verifier, device_id, redirect_uri} — code exchange

    For OAuth mode, exchanges the code for an access_token via
    VK ID API (https://id.vk.com/oauth2/auth), then resolves
    vk_user_id → internal user_id. If the VK user is not yet linked
    to any internal user, auto-registers a new user and links the VK ID.
    """
    service = get_user_settings_service()

    # Mode 1: Re-auth by internal user_id (stored after initial VK OAuth)
    user_id = data.get('user_id')
    if user_id is not None:
        # Verify the user still exists in the database
        summary = service.get_settings_summary(int(user_id))
        if summary is not None:
            return int(user_id)
        return None

    # Mode 2: VK Mini Apps with sign verification
    vk_user_id = data.get('vk_user_id')
    sign = data.get('sign')
    if vk_user_id and sign:
        if not _verify_vk_mini_app_sign(data):
            logger.warning('VK Mini Apps sign verification failed for vk_user_id=%s', vk_user_id)
            return None
        return service.get_user_by_vk_id(int(vk_user_id))

    # Mode 3: Mini Apps without sign (legacy, kept for backward compat)
    vk_id = data.get('vk_user_id')
    if vk_id:
        logger.debug('VK auth without sign verification (legacy mode)')
        return service.get_user_by_vk_id(int(vk_id))

    # Mode 4: VK ID OAuth 2.0 with PKCE code exchange
    code = data.get('code')
    code_verifier = data.get('code_verifier')
    device_id = data.get('device_id', '')
    redirect_uri = data.get('redirect_uri')
    if code and code_verifier and redirect_uri and VK_OAUTH_CLIENT_ID:
        try:
            import httpx

            # Build token exchange payload.
            # Per VK ID docs (Step 5): device_id is REQUIRED for token exchange.
            # It comes from the callback payload (Step 3-4).
            if not device_id:
                logger.warning('VK ID OAuth code exchange: device_id is empty, request will likely fail')
            payload: dict[str, str] = {
                'grant_type': 'authorization_code',
                'code': code,
                'code_verifier': code_verifier,
                'client_id': VK_OAUTH_CLIENT_ID,
                'redirect_uri': redirect_uri,
                'device_id': device_id,
            }

            logger.info(
                'VK ID OAuth code exchange: client_id=%s redirect_uri=%s device_id=%s',
                VK_OAUTH_CLIENT_ID,
                redirect_uri,
                device_id,
            )
            resp = httpx.post(
                'https://id.vk.com/oauth2/auth',
                data=payload,
                timeout=10,
            )
            logger.info('VK ID response status=%s body=%s', resp.status_code, resp.text)
            resp.raise_for_status()
            token_data = resp.json()
            vk_user_id = token_data.get('user_id')
            if not vk_user_id:
                logger.warning('VK ID returned no user_id in: %s', token_data)
                return None

            # Try to find existing internal user linked to this VK ID
            internal_user_id = service.get_user_by_vk_id(int(vk_user_id))
            if internal_user_id is not None:
                return internal_user_id

            # First-time VK user: auto-register with a negative user_id
            # to avoid collision with Telegram user IDs.

            new_user_id = -abs(int(vk_user_id))
            logger.info(
                'VK user %s not found in DB, auto-registering as internal user_id=%s',
                vk_user_id,
                new_user_id,
            )
            service.register_user(new_user_id, username=None)
            service.set_user_vk_id(new_user_id, str(vk_user_id))
            return new_user_id
        except Exception:
            logger.exception('VK ID OAuth code exchange failed')
            return None

    return None


def _authenticate(request: RequestWrapper) -> int | None:
    """Try to authenticate the request.

    Checks Authorization header for auth method and data.
    Header format: "TG <json>" or "VK <json>"
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header:
        return None

    try:
        method, payload_str = auth_header.split(' ', 1)
        payload = json.loads(payload_str)
    except (ValueError, json.JSONDecodeError):
        return None

    if method.upper() == 'TG':
        return _auth_tg(payload)
    elif method.upper() == 'VK':
        return _auth_vk(payload)

    return None


# ─── Auth Endpoint Handlers ────────────────────────────────────────────


def _handle_auth_tg(data: dict) -> ResponseWrapper:
    """POST /api/v1/auth/tg"""
    user_id = _auth_tg(data)
    if user_id is None:
        return _error_response('Telegram authentication failed', 401)
    return _ok_response({'user_id': user_id})


def _handle_auth_vk(data: dict) -> ResponseWrapper:
    """POST /api/v1/auth/vk"""
    user_id = _auth_vk(data)
    if user_id is None:
        return _error_response('VK authentication failed', 401)
    return _ok_response({'user_id': user_id})


# ─── Router ─────────────────────────────────────────────────────────────

# Auth endpoints (no auth required, no service needed)
AUTH_ROUTES: dict[tuple[str, str], Any] = {
    ('POST', '/api/v1/auth/tg'): _handle_auth_tg,
    ('POST', '/api/v1/auth/vk'): _handle_auth_vk,
}

# Protected endpoints — registered via @route decorator in handlers.py
GET_ROUTES = handlers.GET_ROUTES
POST_ROUTES = handlers.POST_ROUTES
DELETE_ROUTES = handlers.DELETE_ROUTES


# ─── Entrypoint ─────────────────────────────────────────────────────────


@request_response_converter
def main(request: RequestWrapper) -> ResponseWrapper:
    """Main entrypoint for Yandex Cloud Function (HTTP trigger)."""

    # CORS preflight
    if request.method == 'OPTIONS':
        return _cors_response()

    body = request.json_ or {}

    # Path is embedded in the body for YC HTTP-triggered functions
    # (the YC gateway puts the original request path in the body JSON).
    # Fall back to request.path for non-YC environments (e.g., CLI).
    path = body.get('path') or request.path

    # Auth endpoints (no auth required)
    auth_handler = AUTH_ROUTES.get((request.method, path))
    if auth_handler:
        return auth_handler(body)

    # All other endpoints require authentication
    user_id = _authenticate(request)
    if user_id is None:
        return _error_response('Unauthorized — provide valid Authorization header', 401)

    # Create service once and inject into handlers
    service = get_user_settings_service()
    method = request.method

    if method == 'GET':
        handler = GET_ROUTES.get(path)
        if handler:
            return handler(service, user_id)
    elif method == 'POST':
        handler = POST_ROUTES.get(path)
        if handler:
            return handler(service, user_id, body)
    elif method == 'DELETE':
        handler = DELETE_ROUTES.get(path)
        if handler:
            return handler(service, user_id, body)

    return _error_response(f'Not found: {method} {path}', 404)
