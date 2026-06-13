"""Conftest for vk_admin_api tests — patches and shared fixtures."""

from unittest.mock import patch

import pytest

from tests.factories.db_factories import (
    GeoDivisionFactory,
    GeoFolderFactory,
    UserFactory,
    UserRegionalPreferenceFactory,
)


@pytest.fixture(autouse=True)
def patch_verify_telegram_data():
    """Patch verify_telegram_data to return True by default for all vk_admin_api tests."""
    with patch('vk_admin_api.main.verify_telegram_data', return_value=True):
        yield


@pytest.fixture
def auth_user():
    """Create a user and return (user, auth_header) tuple.

    Usage:
        def test_something(self, session, auth_user):
            user, auth = auth_user
            resp = _call_main(method='GET', data={'path': '/api/v1/...'}, auth=auth)
    """
    user = UserFactory.create_sync()
    auth = f'TG {{"id": {user.user_id}, "hash": "test", "auth_date": 1000000}}'
    return user, auth


@pytest.fixture
def auth_user_with_region():
    """Create a user subscribed to a region and return (user, auth, folder).

    Usage:
        def test_searches(self, session, auth_user_with_region):
            user, auth, folder = auth_user_with_region
            resp = _call_main(method='GET', data={'path': '/api/v1/searches/active'}, auth=auth)
    """
    user = UserFactory.create_sync()
    auth = f'TG {{"id": {user.user_id}, "hash": "test", "auth_date": 1000000}}'
    folder = GeoFolderFactory.create_sync(folder_type='searches')
    UserRegionalPreferenceFactory.create_sync(user_id=user.user_id, forum_folder_num=folder.folder_id)
    return user, auth, folder
