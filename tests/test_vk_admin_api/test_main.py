"""Tests for VK Admin Panel API (vk_admin_api)."""

import json
from datetime import datetime
from unittest.mock import patch

from _dependencies.commons import TopicType
from tests.common import get_http_request
from tests.factories.db_factories import (
    GeoDivisionFactory,
    GeoFolderFactory,
    SearchFactory,
    SearchFirstPostFactory,
    SearchHealthCheckFactory,
    UserCoordinateFactory,
    UserFactory,
    UserForumAttributeFactory,
    UserPrefAgeFactory,
    UserPreferenceFactory,
    UserPrefRadiusFactory,
    UserPrefTopicTypeFactory,
    UserRegionalPreferenceFactory,
    UserRoleFactory,
)
from vk_admin_api import main

# ─── Helpers ──────────────────────────────────────────────────────────────


def _make_request(
    method: str = 'GET',
    data: dict | None = None,
    auth: str | None = None,
) -> dict:
    """Build a YC-format request dict with optional Authorization header."""
    req = get_http_request(method=method, data=data)
    if auth:
        req['headers'] = {'Authorization': auth}
    else:
        req['headers'] = {}
    return req


def _call_main(method: str, data: dict | None = None, auth: str | None = None) -> dict:
    """Shortcut to call main() and return the parsed response dict."""
    request = _make_request(method=method, data=data, auth=auth)
    resp = main.main(request)
    if resp.get('body'):
        resp['body_parsed'] = json.loads(resp['body'])
    else:
        resp['body_parsed'] = None
    return resp


# ─── CORS ─────────────────────────────────────────────────────────────────


class TestCORS:
    def test_options_preflight(self):
        """OPTIONS request returns 204 with CORS headers."""
        resp = _call_main(method='OPTIONS')

        assert resp['statusCode'] == 204
        assert resp['headers']['Access-Control-Allow-Origin'] == '*'
        assert 'Access-Control-Allow-Methods' in resp['headers']
        assert 'Access-Control-Allow-Headers' in resp['headers']

    def test_options_with_body(self):
        """OPTIONS ignores body and returns 204."""
        request = _make_request(method='OPTIONS', data={'path': '/api/v1/settings'})
        resp = main.main(request)

        assert resp['statusCode'] == 204


# ─── Authentication ───────────────────────────────────────────────────────


class TestAuth:
    def test_auth_tg_success(self):
        """POST /api/v1/auth/tg with valid TG data returns user_id."""
        with patch.object(main, 'verify_telegram_data', return_value=True):
            resp = _call_main(
                method='POST',
                data={'path': '/api/v1/auth/tg', 'id': 12345, 'hash': 'valid'},
            )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['ok'] is True
        assert resp['body_parsed']['data']['user_id'] == 12345

    def test_auth_tg_failure(self):
        """POST /api/v1/auth/tg with invalid hash returns 401."""
        with patch.object(main, 'verify_telegram_data', return_value=False):
            resp = _call_main(
                method='POST',
                data={'path': '/api/v1/auth/tg', 'id': 12345, 'hash': 'invalid'},
            )

        assert resp['statusCode'] == 401
        assert resp['body_parsed']['ok'] is False

    def test_auth_tg_missing_id(self):
        """POST /api/v1/auth/tg without id returns 401."""
        with patch.object(main, 'verify_telegram_data', return_value=True):
            resp = _call_main(
                method='POST',
                data={'path': '/api/v1/auth/tg', 'hash': 'valid'},
            )

        assert resp['statusCode'] == 401

    def test_auth_vk_success(self, session):
        """POST /api/v1/auth/vk with valid vk_id returns user_id."""
        import random

        vk_id = str(random.randint(1000000, 9999999))
        user = UserFactory.create_sync(vk_id=vk_id)
        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/auth/vk', 'vk_user_id': int(vk_id)},
        )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['ok'] is True
        assert resp['body_parsed']['data']['user_id'] == user.user_id

    def test_auth_vk_not_found(self):
        """POST /api/v1/auth/vk with unknown vk_id returns 401."""
        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/auth/vk', 'vk_user_id': 999999},
        )

        assert resp['statusCode'] == 401
        assert resp['body_parsed']['ok'] is False

    def test_auth_vk_missing_id(self):
        """POST /api/v1/auth/vk without vk_user_id returns 401."""
        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/auth/vk'},
        )

        assert resp['statusCode'] == 401

    def test_no_auth_returns_401(self):
        """GET endpoint without auth returns 401."""
        resp = _call_main(method='GET', data={'path': '/api/v1/settings'})

        assert resp['statusCode'] == 401
        assert 'Unauthorized' in resp['body_parsed']['error']

    def test_invalid_auth_header(self):
        """Malformed Authorization header returns 401."""
        resp = _call_main(
            method='GET',
            data={'path': '/api/v1/settings'},
            auth='not-a-valid-header',
        )

        assert resp['statusCode'] == 401


# ─── Settings ─────────────────────────────────────────────────────────────


class TestGetSettings:
    def test_get_settings_full(self, session, auth_user):
        """GET /api/v1/settings returns full settings summary."""
        user, auth = auth_user
        user_id = user.user_id

        # Create geo folder + division so geo_folders_view returns data
        division = GeoDivisionFactory.create_sync(division_name='Тестовый округ')
        folder = GeoFolderFactory.create_sync(
            division_id=division.division_id,
            folder_type='searches',
            folder_subtype='searches all',
        )
        # Subscribe user to this folder
        UserRegionalPreferenceFactory.create_sync(
            user_id=user_id,
            forum_folder_num=folder.folder_id,
        )
        # Add a preference
        UserPreferenceFactory.create_sync(user_id=user_id, preference='status_changes')
        # Add coordinates
        UserCoordinateFactory.create_sync(user_id=user_id, latitude='55.7558', longitude='37.6173')
        # Add radius
        UserPrefRadiusFactory.create_sync(user_id=user_id, radius=50)
        # Add age preference
        UserPrefAgeFactory.create_sync(user_id=user_id, period_min=18, period_max=30)
        # Add topic type
        UserPrefTopicTypeFactory.create_sync(user_id=user_id, topic_type_id=3)
        # Add forum attributes
        UserForumAttributeFactory.create_sync(user_id=user_id, forum_username='testuser', status='verified')
        # Add role
        UserRoleFactory.create_sync(user_id=user_id, role='admin')

        resp = _call_main(method='GET', data={'path': '/api/v1/settings'}, auth=auth)

        assert resp['statusCode'] == 200
        data = resp['body_parsed']['data']
        assert data['user_id'] == user_id
        assert data['role'] is not None
        assert len(data['regions']) >= 1
        assert 'status_changes' in data['preferences']
        assert data['coordinates'] == {'lat': 55.7558, 'lon': 37.6173}
        assert data['radius'] == 50
        assert data['follow_mode'] is False
        assert data['has_forum'] is True
        assert data['forum_username'] == 'testuser'

    def test_get_settings_user_not_found(self):
        """GET /api/v1/settings for non-existent user returns 404."""
        auth = 'TG {"id": 999999999, "hash": "test", "auth_date": 1000000}'
        resp = _call_main(method='GET', data={'path': '/api/v1/settings'}, auth=auth)

        assert resp['statusCode'] == 404
        assert resp['body_parsed']['ok'] is False


# ─── Preferences ──────────────────────────────────────────────────────────


class TestPreferences:
    def test_get_preferences(self, session, auth_user):
        """GET /api/v1/preferences returns list of preferences."""
        user, auth = auth_user
        UserPreferenceFactory.create_sync(user_id=user.user_id, preference='status_changes')
        UserPreferenceFactory.create_sync(user_id=user.user_id, preference='new_searches')

        resp = _call_main(method='GET', data={'path': '/api/v1/preferences'}, auth=auth)

        assert resp['statusCode'] == 200
        prefs = resp['body_parsed']['data']
        assert 'status_changes' in prefs
        assert 'new_searches' in prefs

    def test_post_preference_enable(self, session, auth_user):
        """POST /api/v1/preferences enables a preference."""
        user, auth = auth_user

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/preferences', 'preference': 'status_changes', 'enabled': True},
            auth=auth,
        )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['preference'] == 'status_changes'
        assert resp['body_parsed']['data']['enabled'] is True

    def test_post_preference_disable(self, session, auth_user):
        """POST /api/v1/preferences disables a preference."""
        user, auth = auth_user
        UserPreferenceFactory.create_sync(user_id=user.user_id, preference='status_changes')

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/preferences', 'preference': 'status_changes', 'enabled': False},
            auth=auth,
        )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['enabled'] is False

    def test_post_preference_missing_field(self, session, auth_user):
        """POST /api/v1/preferences without 'preference' field returns 400."""
        user, auth = auth_user

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/preferences', 'enabled': True},
            auth=auth,
        )

        assert resp['statusCode'] == 400

    def test_delete_preferences(self, session, auth_user):
        """DELETE /api/v1/preferences removes specified preferences."""
        user, auth = auth_user
        UserPreferenceFactory.create_sync(user_id=user.user_id, preference='status_changes')
        UserPreferenceFactory.create_sync(user_id=user.user_id, preference='new_searches')

        resp = _call_main(
            method='DELETE',
            data={'path': '/api/v1/preferences', 'preferences': ['status_changes']},
            auth=auth,
        )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['deleted'] == 1

    def test_delete_all_preferences(self, session, auth_user):
        """DELETE /api/v1/preferences with empty list deletes all."""
        user, auth = auth_user
        UserPreferenceFactory.create_sync(user_id=user.user_id, preference='status_changes')

        resp = _call_main(
            method='DELETE',
            data={'path': '/api/v1/preferences', 'preferences': []},
            auth=auth,
        )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['deleted'] == 'all'


# ─── Regions ──────────────────────────────────────────────────────────────


class TestRegions:
    def test_get_regions(self, session, auth_user):
        """GET /api/v1/regions returns geo folders with subscription status."""
        user, auth = auth_user
        division = GeoDivisionFactory.create_sync(division_name='Тестовый округ')
        folder = GeoFolderFactory.create_sync(
            division_id=division.division_id,
            folder_type='searches',
            folder_subtype='searches all',
        )
        UserRegionalPreferenceFactory.create_sync(
            user_id=user.user_id,
            forum_folder_num=folder.folder_id,
        )

        resp = _call_main(method='GET', data={'path': '/api/v1/regions'}, auth=auth)

        assert resp['statusCode'] == 200
        regions = resp['body_parsed']['data']
        assert len(regions) >= 1
        subscribed = [r for r in regions if r['subscribed']]
        assert any(r['id'] == folder.folder_id for r in subscribed)

    def test_post_regions_toggle(self, session, auth_user):
        """POST /api/v1/regions/toggle toggles a region subscription."""
        user, auth = auth_user
        division = GeoDivisionFactory.create_sync(division_name='Тестовый округ')
        GeoFolderFactory.create_sync(
            division_id=division.division_id,
            folder_type='searches',
            folder_subtype='searches all',
        )

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/regions/toggle', 'region_name': 'Тестовый округ'},
            auth=auth,
        )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['region_name'] == 'Тестовый округ'

    def test_post_regions_toggle_missing_name(self, session, auth_user):
        """POST /api/v1/regions/toggle without region_name returns 400."""
        user, auth = auth_user

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/regions/toggle'},
            auth=auth,
        )

        assert resp['statusCode'] == 400


# ─── Coordinates ──────────────────────────────────────────────────────────


class TestCoordinates:
    def test_get_coordinates_none(self, session, auth_user):
        """GET /api/v1/coordinates returns None when no coords saved."""
        user, auth = auth_user

        resp = _call_main(method='GET', data={'path': '/api/v1/coordinates'}, auth=auth)

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data'] is None

    def test_get_coordinates_existing(self, session, auth_user):
        """GET /api/v1/coordinates returns saved coordinates."""
        user, auth = auth_user
        UserCoordinateFactory.create_sync(user_id=user.user_id, latitude='55.7558', longitude='37.6173')

        resp = _call_main(method='GET', data={'path': '/api/v1/coordinates'}, auth=auth)

        assert resp['statusCode'] == 200
        data = resp['body_parsed']['data']
        assert data['lat'] == 55.7558
        assert data['lon'] == 37.6173

    def test_post_coordinates(self, session, auth_user):
        """POST /api/v1/coordinates saves coordinates."""
        user, auth = auth_user

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/coordinates', 'latitude': 55.7527, 'longitude': 37.6229},
            auth=auth,
        )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['latitude'] == 55.7527

    def test_post_coordinates_missing_fields(self, session, auth_user):
        """POST /api/v1/coordinates without lat/lon returns 400."""
        user, auth = auth_user

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/coordinates', 'latitude': 55.7527},
            auth=auth,
        )

        assert resp['statusCode'] == 400

    def test_delete_coordinates(self, session, auth_user):
        """DELETE /api/v1/coordinates deletes saved coordinates."""
        user, auth = auth_user
        UserCoordinateFactory.create_sync(user_id=user.user_id, latitude='55.7558', longitude='37.6173')

        resp = _call_main(method='DELETE', data={'path': '/api/v1/coordinates'}, auth=auth)

        assert resp['statusCode'] == 200


# ─── Radius ───────────────────────────────────────────────────────────────


class TestRadius:
    def test_get_radius_none(self, session, auth_user):
        """GET /api/v1/radius returns None when no radius saved."""
        user, auth = auth_user

        resp = _call_main(method='GET', data={'path': '/api/v1/radius'}, auth=auth)

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['radius'] is None

    def test_get_radius_existing(self, session, auth_user):
        """GET /api/v1/radius returns saved radius."""
        user, auth = auth_user
        UserPrefRadiusFactory.create_sync(user_id=user.user_id, radius=75)

        resp = _call_main(method='GET', data={'path': '/api/v1/radius'}, auth=auth)

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['radius'] == 75

    def test_post_radius(self, session, auth_user):
        """POST /api/v1/radius saves radius."""
        user, auth = auth_user

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/radius', 'radius': 100},
            auth=auth,
        )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['radius'] == 100

    def test_post_radius_missing_field(self, session, auth_user):
        """POST /api/v1/radius without radius field returns 400."""
        user, auth = auth_user

        resp = _call_main(method='POST', data={'path': '/api/v1/radius'}, auth=auth)

        assert resp['statusCode'] == 400

    def test_delete_radius(self, session, auth_user):
        """DELETE /api/v1/radius deletes saved radius."""
        user, auth = auth_user
        UserPrefRadiusFactory.create_sync(user_id=user.user_id, radius=50)

        resp = _call_main(method='DELETE', data={'path': '/api/v1/radius'}, auth=auth)

        assert resp['statusCode'] == 200


# ─── Age Preferences ──────────────────────────────────────────────────────


class TestAgePreferences:
    def test_get_age_preferences(self, session, auth_user):
        """GET /api/v1/age-preferences returns age periods."""
        user, auth = auth_user
        UserPrefAgeFactory.create_sync(user_id=user.user_id, period_min=18, period_max=30)
        UserPrefAgeFactory.create_sync(user_id=user.user_id, period_min=31, period_max=50)

        resp = _call_main(method='GET', data={'path': '/api/v1/age-preferences'}, auth=auth)

        assert resp['statusCode'] == 200
        ages = resp['body_parsed']['data']
        assert len(ages) >= 2

    def test_post_age_preferences(self, session, auth_user):
        """POST /api/v1/age-preferences saves an age period."""
        user, auth = auth_user

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/age-preferences', 'min_age': 18, 'max_age': 30},
            auth=auth,
        )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['min_age'] == 18

    def test_post_age_preferences_missing_fields(self, session, auth_user):
        """POST /api/v1/age-preferences without min/max returns 400."""
        user, auth = auth_user

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/age-preferences', 'min_age': 18},
            auth=auth,
        )

        assert resp['statusCode'] == 400

    def test_delete_age_preferences(self, session, auth_user):
        """DELETE /api/v1/age-preferences deletes an age period."""
        user, auth = auth_user
        UserPrefAgeFactory.create_sync(user_id=user.user_id, period_min=18, period_max=30)

        resp = _call_main(
            method='DELETE',
            data={'path': '/api/v1/age-preferences', 'min_age': 18, 'max_age': 30},
            auth=auth,
        )

        assert resp['statusCode'] == 200

    def test_delete_age_preferences_missing_fields(self, session, auth_user):
        """DELETE /api/v1/age-preferences without min/max returns 400."""
        user, auth = auth_user

        resp = _call_main(
            method='DELETE',
            data={'path': '/api/v1/age-preferences'},
            auth=auth,
        )

        assert resp['statusCode'] == 400


# ─── Topic Types ──────────────────────────────────────────────────────────


class TestTopicTypes:
    def test_get_topic_types(self, session, auth_user):
        """GET /api/v1/topic-types returns topic type preferences."""
        user, auth = auth_user
        UserPrefTopicTypeFactory.create_sync(user_id=user.user_id, topic_type_id=3)

        resp = _call_main(method='GET', data={'path': '/api/v1/topic-types'}, auth=auth)

        assert resp['statusCode'] == 200
        assert 3 in resp['body_parsed']['data']

    def test_post_topic_types(self, session, auth_user):
        """POST /api/v1/topic-types saves a topic type."""
        user, auth = auth_user

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/topic-types', 'topic_type_id': 3},
            auth=auth,
        )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['topic_type_id'] == 3

    def test_post_topic_types_missing_field(self, session, auth_user):
        """POST /api/v1/topic-types without topic_type_id returns 400."""
        user, auth = auth_user

        resp = _call_main(method='POST', data={'path': '/api/v1/topic-types'}, auth=auth)

        assert resp['statusCode'] == 400

    def test_delete_topic_types(self, session, auth_user):
        """DELETE /api/v1/topic-types deletes a topic type."""
        user, auth = auth_user
        UserPrefTopicTypeFactory.create_sync(user_id=user.user_id, topic_type_id=3)

        resp = _call_main(
            method='DELETE',
            data={'path': '/api/v1/topic-types', 'topic_type_id': 3},
            auth=auth,
        )

        assert resp['statusCode'] == 200

    def test_delete_topic_types_missing_field(self, session, auth_user):
        """DELETE /api/v1/topic-types without topic_type_id returns 400."""
        user, auth = auth_user

        resp = _call_main(method='DELETE', data={'path': '/api/v1/topic-types'}, auth=auth)

        assert resp['statusCode'] == 400


# ─── Follow Mode ──────────────────────────────────────────────────────────


class TestFollowMode:
    def test_get_follow_mode_default(self, session, auth_user):
        """GET /api/v1/follow-mode returns False by default."""
        user, auth = auth_user

        resp = _call_main(method='GET', data={'path': '/api/v1/follow-mode'}, auth=auth)

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['enabled'] is False

    def test_post_follow_mode_enable(self, session, auth_user):
        """POST /api/v1/follow-mode enables follow mode."""
        user, auth = auth_user

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/follow-mode', 'enabled': True},
            auth=auth,
        )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['enabled'] is True

    def test_post_follow_mode_disable(self, session, auth_user):
        """POST /api/v1/follow-mode disables follow mode."""
        user, auth = auth_user

        resp = _call_main(
            method='POST',
            data={'path': '/api/v1/follow-mode', 'enabled': False},
            auth=auth,
        )

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data']['enabled'] is False


# ─── Active Searches ──────────────────────────────────────────────────────


class TestActiveSearches:
    def test_get_active_searches_no_regions(self, session, auth_user):
        """GET /api/v1/searches/active returns empty list when user has no regions."""
        user, auth = auth_user

        resp = _call_main(method='GET', data={'path': '/api/v1/searches/active'}, auth=auth)

        assert resp['statusCode'] == 200
        assert resp['body_parsed']['data'] == []

    def test_get_active_searches_with_data(self, session, auth_user_with_region):
        """GET /api/v1/searches/active returns active searches for user's regions."""
        user, auth, folder = auth_user_with_region

        # Create an active search in that folder
        search = SearchFactory.create_sync(
            forum_folder_id=folder.folder_id,
            status='Active',
            topic_type_id=TopicType.search_patrol,
            search_start_time=datetime.now(),
            display_name='Test Search',
        )
        SearchFirstPostFactory.create_sync(search_id=search.search_forum_num, actual=True)
        SearchHealthCheckFactory.create_sync(search_forum_num=search.search_forum_num, status='ok')

        resp = _call_main(method='GET', data={'path': '/api/v1/searches/active'}, auth=auth)

        assert resp['statusCode'] == 200
        searches = resp['body_parsed']['data']
        assert len(searches) >= 1
        assert any(s['search_id'] == search.search_forum_num for s in searches)

    def test_get_active_searches_filters_finished(self, session, auth_user_with_region):
        """GET /api/v1/searches/active excludes finished searches."""
        user, auth, folder = auth_user_with_region

        # Create a finished search (should be excluded)
        SearchFactory.create_sync(
            forum_folder_id=folder.folder_id,
            status='Завершен',
            topic_type_id=TopicType.search_patrol,
            search_start_time=datetime.now(),
        )

        resp = _call_main(method='GET', data={'path': '/api/v1/searches/active'}, auth=auth)

        assert resp['statusCode'] == 200
        searches = resp['body_parsed']['data']
        # Finished searches should not appear
        finished = [s for s in searches if s['status'] == 'Завершен']
        assert len(finished) == 0


# ─── User Info ────────────────────────────────────────────────────────────


class TestUserInfo:
    def test_get_user_info_basic(self, session, auth_user):
        """GET /api/v1/user/info returns basic user info."""
        user, auth = auth_user
        user_id = user.user_id

        resp = _call_main(method='GET', data={'path': '/api/v1/user/info'}, auth=auth)

        assert resp['statusCode'] == 200
        data = resp['body_parsed']['data']
        assert data['user_id'] == user_id
        assert data['role'] is not None
        assert data['forum_username'] is None

    def test_get_user_info_with_forum(self, session, auth_user):
        """GET /api/v1/user/info returns forum info when linked."""
        user, auth = auth_user
        user_id = user.user_id
        UserForumAttributeFactory.create_sync(
            user_id=user_id, forum_username='forum_user', forum_user_id=42, status='verified'
        )

        resp = _call_main(method='GET', data={'path': '/api/v1/user/info'}, auth=auth)

        assert resp['statusCode'] == 200
        data = resp['body_parsed']['data']
        assert data['forum_username'] == 'forum_user'
        assert data['forum_user_id'] == 42

    def test_get_user_info_with_sys_roles(self, session, auth_user):
        """GET /api/v1/user/info returns system roles."""
        user, auth = auth_user
        user_id = user.user_id
        UserRoleFactory.create_sync(user_id=user_id, role='admin')
        UserRoleFactory.create_sync(user_id=user_id, role='tester')

        resp = _call_main(method='GET', data={'path': '/api/v1/user/info'}, auth=auth)

        assert resp['statusCode'] == 200
        data = resp['body_parsed']['data']
        assert 'admin' in data['sys_roles']
        assert 'tester' in data['sys_roles']


# ─── 404 ──────────────────────────────────────────────────────────────────


class TestNotFound:
    def test_unknown_get_route(self, session, auth_user):
        """GET to unknown path returns 404."""
        user, auth = auth_user

        resp = _call_main(method='GET', data={'path': '/api/v1/nonexistent'}, auth=auth)

        assert resp['statusCode'] == 404

    def test_unknown_post_route(self, session, auth_user):
        """POST to unknown path returns 404."""
        user, auth = auth_user

        resp = _call_main(method='POST', data={'path': '/api/v1/nonexistent'}, auth=auth)

        assert resp['statusCode'] == 404

    def test_unknown_delete_route(self, session, auth_user):
        """DELETE to unknown path returns 404."""
        user, auth = auth_user

        resp = _call_main(method='DELETE', data={'path': '/api/v1/nonexistent'}, auth=auth)

        assert resp['statusCode'] == 404
