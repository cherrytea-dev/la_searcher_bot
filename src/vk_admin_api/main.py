"""VK Admin Panel API — REST endpoints for managing user notification settings.

This function provides a JSON API for a web front-end (admin panel)
that replaces VK Bot's keyboard-based settings UI.

Authentication:
  - Telegram Login Widget (HMAC-SHA256 verification)
  - VK OAuth 2.0 (code exchange, works in any browser)
  - VK Mini Apps (legacy, direct vk_user_id)

Endpoints:
  POST /api/v1/auth/tg       — Authenticate via Telegram Login Widget
  POST /api/v1/auth/vk       — Authenticate via VK (OAuth code or Mini Apps)
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


def _auth_vk(data: dict) -> int | None:
    """Authenticate via VK.

    Supports two modes:
    1. Mini Apps (legacy): {vk_user_id: int} — direct user ID
    2. OAuth 2.0 (browser): {code: str, redirect_uri: str} — code exchange

    For OAuth mode, exchanges the code for an access_token via
    VK OAuth API, then resolves vk_user_id → internal user_id.
    """
    # Mode 1: Mini Apps (direct vk_user_id)
    vk_id = data.get('vk_user_id')
    if vk_id:
        service = get_user_settings_service()
        return service.get_user_by_vk_id(int(vk_id))

    # Mode 2: OAuth 2.0 code exchange
    code = data.get('code')
    redirect_uri = data.get('redirect_uri')
    if code and redirect_uri and VK_OAUTH_CLIENT_ID and VK_OAUTH_CLIENT_SECRET:
        try:
            import httpx

            resp = httpx.post(
                'https://oauth.vk.com/access_token',
                data={
                    'client_id': VK_OAUTH_CLIENT_ID,
                    'client_secret': VK_OAUTH_CLIENT_SECRET,
                    'code': code,
                    'redirect_uri': redirect_uri,
                },
                timeout=10,
            )
            resp.raise_for_status()
            token_data = resp.json()
            vk_user_id = token_data.get('user_id')
            if not vk_user_id:
                return None
            service = get_user_settings_service()
            return service.get_user_by_vk_id(int(vk_user_id))
        except Exception:
            logger.exception('VK OAuth code exchange failed')
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

    # Auth endpoints (no auth required)
    auth_handler = AUTH_ROUTES.get((request.method, body.get('path', '')))
    if auth_handler:
        return auth_handler(body)

    # All other endpoints require authentication
    user_id = _authenticate(request)
    if user_id is None:
        return _error_response('Unauthorized — provide valid Authorization header', 401)

    # Create service once and inject into handlers
    service = get_user_settings_service()
    path = body.get('path', '')
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
