"""Endpoint handlers for VK Admin Panel API.

Each handler receives a UserSettingsService instance as the first argument,
plus the user_id and optional request body data.

Routes are registered via the @route decorator:
    @route('GET', '/settings')
    def handle_get_settings(service: UserSettingsService, user_id: int) -> ResponseWrapper:
        ...

The API_PREFIX constant is prepended automatically, so you only specify the path
relative to the API root.
"""

import json
import logging
from typing import Any, Callable

import sqlalchemy

from _dependencies.commons import sqlalchemy_get_pool
from _dependencies.misc import ResponseWrapper
from _dependencies.services.user_settings_service import (
    AgePeriod,
    UserSettingsService,
)

logger = logging.getLogger(__name__)


# ─── Route Registration ─────────────────────────────────────────────────


# API prefix prepended to all route paths
API_PREFIX = '/api/v1'

# Route tables populated by the @route decorator.
# GET handlers: (service, user_id) -> ResponseWrapper
# POST/DELETE handlers: (service, user_id, data) -> ResponseWrapper
GET_ROUTES: dict[str, Callable[..., ResponseWrapper]] = {}
POST_ROUTES: dict[str, Callable[..., ResponseWrapper]] = {}
DELETE_ROUTES: dict[str, Callable[..., ResponseWrapper]] = {}


def route(method: str, path: str) -> Callable:
    """Decorator that registers a handler function in the appropriate route table.

    The API_PREFIX ('/api/v1') is prepended automatically.
    Usage:
        @route('GET', '/settings')
        def handle_get_settings(service, user_id):
            ...
    """
    table = _route_table(method)
    full_path = API_PREFIX + path

    def decorator(func: Callable[..., ResponseWrapper]) -> Callable[..., ResponseWrapper]:
        table[full_path] = func
        return func

    return decorator


def _route_table(method: str) -> dict[str, Callable[..., ResponseWrapper]]:
    if method == 'GET':
        return GET_ROUTES
    elif method == 'POST':
        return POST_ROUTES
    elif method == 'DELETE':
        return DELETE_ROUTES
    raise ValueError(f'Unsupported HTTP method: {method}')


# ─── Response Helpers ───────────────────────────────────────────────────


def _ok_response(data: Any = None) -> ResponseWrapper:
    body = json.dumps({'ok': True, 'data': data}, ensure_ascii=False, default=str)
    return ResponseWrapper(body, 200, {'Content-Type': 'application/json'})


def _error_response(message: str, status: int = 400) -> ResponseWrapper:
    body = json.dumps({'ok': False, 'error': message}, ensure_ascii=False)
    return ResponseWrapper(body, status, {'Content-Type': 'application/json'})


# ─── Settings ───────────────────────────────────────────────────────────


@route('GET', '/settings')
def handle_get_settings(service: UserSettingsService, user_id: int) -> ResponseWrapper:
    """GET /settings — full settings summary."""
    summary = service.get_settings_summary(user_id)
    if summary is None:
        return _error_response('User not found', 404)

    regions = service.get_user_regions(user_id)
    geo_folders = service.get_geo_folders()
    preferences = service.get_all_user_preferences(user_id)
    coords = service.get_coordinates(user_id)
    radius = service.get_radius(user_id)
    age_prefs = service.get_age_preferences(user_id)
    topic_types = service.get_topic_types(user_id)
    follow_mode = service.get_search_follow_mode(user_id)
    role = service.get_user_role(user_id)
    forum_attrs = service.get_forum_attributes(user_id)

    # Build region list with subscription status
    region_list = []
    for fid, name in geo_folders:
        if name is not None:
            region_list.append(
                {
                    'id': fid,
                    'name': name,
                    'subscribed': fid in regions,
                }
            )

    # Build age preferences list
    age_list = []
    for min_age, max_age in age_prefs:
        age_list.append(
            {
                'min_age': min_age,
                'max_age': max_age,
            }
        )

    result = {
        'user_id': user_id,
        'role': role,
        'regions': region_list,
        'preferences': preferences,
        'coordinates': {'lat': float(coords[0]), 'lon': float(coords[1])} if coords else None,
        'radius': radius,
        'age_preferences': age_list,
        'topic_types': topic_types,
        'follow_mode': follow_mode,
        'has_forum': forum_attrs is not None,
        'forum_username': forum_attrs[0] if forum_attrs else None,
    }
    return _ok_response(result)


# ─── Preferences ────────────────────────────────────────────────────────


@route('GET', '/preferences')
def handle_get_preferences(service: UserSettingsService, user_id: int) -> ResponseWrapper:
    """GET /preferences"""
    prefs = service.get_all_user_preferences(user_id)
    return _ok_response(prefs)


@route('POST', '/preferences')
def handle_post_preferences(service: UserSettingsService, user_id: int, data: dict) -> ResponseWrapper:
    """POST /preferences — toggle a preference on/off.

    Body: {"preference": "status_changes", "enabled": true}
    """
    preference = data.get('preference')
    enabled = data.get('enabled', True)
    if not preference:
        return _error_response('Missing "preference" field')

    if enabled:
        service.save_preference(user_id, preference)
    else:
        service.delete_preferences(user_id, [preference])

    return _ok_response({'preference': preference, 'enabled': enabled})


@route('DELETE', '/preferences')
def handle_delete_preferences(service: UserSettingsService, user_id: int, data: dict) -> ResponseWrapper:
    """DELETE /preferences

    Body: {"preferences": ["status_changes", "first_post_changes"]}
    If preferences list is empty, deletes ALL preferences.
    """
    preferences = data.get('preferences', [])
    service.delete_preferences(user_id, preferences)
    return _ok_response({'deleted': len(preferences) if preferences else 'all'})


# ─── Regions ────────────────────────────────────────────────────────────


@route('GET', '/regions')
def handle_get_regions(service: UserSettingsService, user_id: int) -> ResponseWrapper:
    """GET /regions — list all geo folders + user's subscriptions."""
    geo_folders = service.get_geo_folders()
    user_regions = service.get_user_regions(user_id)

    region_list = []
    for fid, name in geo_folders:
        if name is not None:
            region_list.append(
                {
                    'id': fid,
                    'name': name,
                    'subscribed': fid in user_regions,
                }
            )

    return _ok_response(region_list)


@route('POST', '/regions/toggle')
def handle_post_regions_toggle(service: UserSettingsService, user_id: int, data: dict) -> ResponseWrapper:
    """POST /regions/toggle — toggle a region subscription.

    Body: {"region_name": "Москва"}
    """
    region_name = data.get('region_name')
    if not region_name:
        return _error_response('Missing "region_name" field')

    geo_folders = service.get_geo_folders()
    folder_dict: dict[str, tuple[int, ...]] = {}
    for fid, name in geo_folders:
        if name is not None:
            folder_dict[name] = (fid,)

    success = service.toggle_region_by_name(user_id, region_name, folder_dict)
    if not success:
        return _error_response('Cannot toggle region (not found or last remaining region)')

    return _ok_response({'region_name': region_name})


# ─── Coordinates ────────────────────────────────────────────────────────


@route('GET', '/coordinates')
def handle_get_coordinates(service: UserSettingsService, user_id: int) -> ResponseWrapper:
    """GET /coordinates"""
    coords = service.get_coordinates(user_id)
    if coords:
        return _ok_response({'lat': float(coords[0]), 'lon': float(coords[1])})
    return _ok_response(None)


@route('POST', '/coordinates')
def handle_post_coordinates(service: UserSettingsService, user_id: int, data: dict) -> ResponseWrapper:
    """POST /coordinates — save home coordinates.

    Body: {"latitude": 55.7527, "longitude": 37.6229}
    """
    lat = data.get('latitude')
    lon = data.get('longitude')
    if lat is None or lon is None:
        return _error_response('Missing "latitude" or "longitude"')

    service.save_coordinates(user_id, float(lat), float(lon))
    return _ok_response({'latitude': lat, 'longitude': lon})


@route('DELETE', '/coordinates')
def handle_delete_coordinates(service: UserSettingsService, user_id: int, data: dict) -> ResponseWrapper:
    """DELETE /coordinates"""
    service.delete_coordinates(user_id)
    return _ok_response(None)


# ─── Radius ─────────────────────────────────────────────────────────────


@route('GET', '/radius')
def handle_get_radius(service: UserSettingsService, user_id: int) -> ResponseWrapper:
    """GET /radius"""
    radius = service.get_radius(user_id)
    return _ok_response({'radius': radius})


@route('POST', '/radius')
def handle_post_radius(service: UserSettingsService, user_id: int, data: dict) -> ResponseWrapper:
    """POST /radius — save notification radius.

    Body: {"radius": 50}
    """
    radius = data.get('radius')
    if radius is None:
        return _error_response('Missing "radius" field')

    service.save_radius(user_id, int(radius))
    return _ok_response({'radius': radius})


@route('DELETE', '/radius')
def handle_delete_radius(service: UserSettingsService, user_id: int, data: dict) -> ResponseWrapper:
    """DELETE /radius"""
    service.delete_radius(user_id)
    return _ok_response(None)


# ─── Age Preferences ────────────────────────────────────────────────────


@route('GET', '/age-preferences')
def handle_get_age_preferences(service: UserSettingsService, user_id: int) -> ResponseWrapper:
    """GET /age-preferences"""
    age_prefs = service.get_age_preferences(user_id)
    age_list = [{'min_age': min_a, 'max_age': max_a} for min_a, max_a in age_prefs]
    return _ok_response(age_list)


@route('POST', '/age-preferences')
def handle_post_age_preferences(service: UserSettingsService, user_id: int, data: dict) -> ResponseWrapper:
    """POST /age-preferences — save an age period.

    Body: {"min_age": 18, "max_age": 30, "name": "young"}
    """
    min_age = data.get('min_age')
    max_age = data.get('max_age')
    if min_age is None or max_age is None:
        return _error_response('Missing "min_age" or "max_age"')

    period = AgePeriod(
        description=data.get('description', ''),
        name=data.get('name', ''),
        min_age=int(min_age),
        max_age=int(max_age),
        order=data.get('order', 0),
    )
    service.save_age_preference(user_id, period)
    return _ok_response({'min_age': min_age, 'max_age': max_age})


@route('DELETE', '/age-preferences')
def handle_delete_age_preferences(service: UserSettingsService, user_id: int, data: dict) -> ResponseWrapper:
    """DELETE /age-preferences — delete an age period.

    Body: {"min_age": 18, "max_age": 30}
    """
    min_age = data.get('min_age')
    max_age = data.get('max_age')
    if min_age is None or max_age is None:
        return _error_response('Missing "min_age" or "max_age"')

    period = AgePeriod(
        description='',
        name='',
        min_age=int(min_age),
        max_age=int(max_age),
        order=0,
    )
    service.delete_age_preference(user_id, period)
    return _ok_response({'min_age': min_age, 'max_age': max_age})


# ─── Topic Types ────────────────────────────────────────────────────────


@route('GET', '/topic-types')
def handle_get_topic_types(service: UserSettingsService, user_id: int) -> ResponseWrapper:
    """GET /topic-types"""
    types = service.get_topic_types(user_id)
    return _ok_response(types)


@route('POST', '/topic-types')
def handle_post_topic_types(service: UserSettingsService, user_id: int, data: dict) -> ResponseWrapper:
    """POST /topic-types — save a topic type preference.

    Body: {"topic_type_id": 3}
    """
    type_id = data.get('topic_type_id')
    if type_id is None:
        return _error_response('Missing "topic_type_id" field')

    service.save_topic_type(user_id, int(type_id))
    return _ok_response({'topic_type_id': type_id})


@route('DELETE', '/topic-types')
def handle_delete_topic_types(service: UserSettingsService, user_id: int, data: dict) -> ResponseWrapper:
    """DELETE /topic-types — delete a topic type preference.

    Body: {"topic_type_id": 3}
    """
    type_id = data.get('topic_type_id')
    if type_id is None:
        return _error_response('Missing "topic_type_id" field')

    service.delete_topic_type(user_id, int(type_id))
    return _ok_response({'topic_type_id': type_id})


# ─── Follow Mode ────────────────────────────────────────────────────────


@route('GET', '/follow-mode')
def handle_get_follow_mode(service: UserSettingsService, user_id: int) -> ResponseWrapper:
    """GET /follow-mode"""
    enabled = service.get_search_follow_mode(user_id)
    return _ok_response({'enabled': enabled})


@route('POST', '/follow-mode')
def handle_post_follow_mode(service: UserSettingsService, user_id: int, data: dict) -> ResponseWrapper:
    """POST /follow-mode — toggle search follow mode.

    Body: {"enabled": true}
    """
    enabled = data.get('enabled', True)
    if enabled:
        service.set_search_follow_mode(user_id, True)
    else:
        service.delete_search_follow_mode(user_id)
    return _ok_response({'enabled': enabled})


# ─── Active Searches ────────────────────────────────────────────────────


@route('GET', '/searches/active')
def handle_get_active_searches(service: UserSettingsService, user_id: int) -> ResponseWrapper:
    """GET /searches/active — get active searches for user's regions."""
    pool = sqlalchemy_get_pool()
    with pool.connect() as conn:
        user_regions = service.get_user_regions(user_id)

        if not user_regions:
            return _ok_response([])

        # Build individual numbered placeholders for IN clause
        # SQLAlchemy 1.4 text() doesn't support = ANY(:param) with list params
        placeholders = ', '.join(f':r{i}' for i in range(len(user_regions)))
        params = {f'r{i}': val for i, val in enumerate(user_regions)}

        query = f"""
            SELECT s.search_forum_num, s.display_name, s.status, s.family_name,
                   s.search_start_time, s.forum_folder_id, s.topic_type, s.topic_type_id,
                   sfp.content
            FROM searches s
            LEFT JOIN search_first_posts sfp ON s.search_forum_num = sfp.search_id AND sfp.actual = True
            LEFT JOIN search_health_check shc ON s.search_forum_num = shc.search_forum_num
            WHERE s.forum_folder_id IN ({placeholders})
              AND s.status NOT IN ('НЖ', 'НП', 'Завершен', 'Найден')
              AND s.topic_type_id != 1
              AND (shc.status IS NULL OR shc.status IN ('ok', 'regular'))
            ORDER BY s.search_start_time DESC
            LIMIT 50
        """
        result = conn.execute(sqlalchemy.text(query), params)
        rows = result.fetchall()

    searches = []
    for row in rows:
        searches.append(
            {
                'search_id': row[0],
                'display_name': row[1] or '',
                'status': row[2],
                'family_name': row[3] or '',
                'start_time': str(row[4]) if row[4] else None,
                'folder_id': row[5],
                'topic_type': row[6],
                'topic_type_id': row[7],
            }
        )

    return _ok_response(searches)


# ─── User Info ──────────────────────────────────────────────────────────


@route('GET', '/user/info')
def handle_get_user_info(service: UserSettingsService, user_id: int) -> ResponseWrapper:
    """GET /user/info — basic user info."""
    role = service.get_user_role(user_id)
    regions = service.get_user_regions(user_id)
    forum_attrs = service.get_forum_attributes(user_id)
    sys_roles = service.get_user_sys_roles(user_id)

    return _ok_response(
        {
            'user_id': user_id,
            'role': role,
            'regions': regions,
            'forum_username': forum_attrs[0] if forum_attrs else None,
            'forum_user_id': forum_attrs[1] if forum_attrs else None,
            'sys_roles': sys_roles,
        }
    )
