"""Tests for the VK bot DBClient (composed from mixins)."""

from random import randint

import pytest
from sqlalchemy.orm import Session

from _dependencies.common.commons import SearchFollowingMode
from tests.common import fake, find_model
from tests.factories import db_factories, db_models
from vk_bot._utils.database import DBClient, db
from vk_bot._utils.database_common import AgePeriod


@pytest.fixture(scope='session')
def settings_service() -> DBClient:
    """Return the singleton DBClient instance (replaces old UserSettingsService)."""
    return db()


@pytest.fixture
def user_id() -> int:
    return randint(1, 1_000_000)


# =============================================================================
# Registration & Onboarding
# =============================================================================


class TestCheckIfNewUser:
    def test_new_user_returns_true(self, settings_service: DBClient):
        user_id = fake.pyint()
        assert settings_service.check_if_new_user(user_id) is True

    def test_existing_user_returns_false(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        assert settings_service.check_if_new_user(user_id) is False


class TestGetOnboardingStep:
    def test_no_onboarding_step(self, settings_service: DBClient, user_id: int):
        step_id, step_name = settings_service.get_onboarding_step(user_id)
        assert step_id == 99
        assert step_name is None

    def test_existing_onboarding_step(self, settings_service: DBClient, user_id: int):
        db_factories.UserOnboardingFactory.create_sync(user_id=user_id, step_id=10, step_name='role_set')
        step_id, step_name = settings_service.get_onboarding_step(user_id)
        assert step_id == 10
        assert step_name == 'role_set'


class TestSaveUserRole:
    def test_save_member_role(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        result = settings_service.save_user_role(user_id, 'member')
        assert result == 'member'

    def test_save_new_member_role(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        result = settings_service.save_user_role(user_id, 'new_member')
        assert result == 'new_member'

    def test_save_relative_role(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        result = settings_service.save_user_role(user_id, 'relative')
        assert result == 'relative'

    def test_save_unknown_role(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        result = settings_service.save_user_role(user_id, 'unknown_role')
        # The mixin stores the role as-is (no mapping to 'other')
        assert result == 'unknown_role'


class TestGetUserRole:
    def test_no_role(self, settings_service: DBClient, user_id: int):
        # UserFactory sets role='new_member' by default, so use a user_id
        # that doesn't exist in DB to test "no role" scenario
        nonexistent_id = user_id + 999999
        role = settings_service.get_user_role(nonexistent_id)
        assert role is None

    def test_existing_role(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id, role='member')
        role = settings_service.get_user_role(user_id)
        assert role == 'member'


class TestGetUserRegions:
    def test_no_regions(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        regions = settings_service.get_user_regions(user_id)
        assert regions == []

    def test_with_regions(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id, forum_folder_num=1)
        db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id, forum_folder_num=2)
        regions = settings_service.get_user_regions(user_id)
        assert sorted(regions) == [1, 2]


class TestAddRegion:
    def test_add_region(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.add_region(user_id, 1)
        regions = settings_service.get_user_regions(user_id)
        assert regions == [1]

    def test_add_duplicate_region(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.add_region(user_id, 1)
        settings_service.add_region(user_id, 1)
        regions = settings_service.get_user_regions(user_id)
        # No unique constraint on (user_id, forum_folder_num), so duplicates are allowed
        assert regions == [1, 1]


class TestRemoveRegion:
    def test_remove_region(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.add_region(user_id, 1)
        settings_service.add_region(user_id, 2)
        settings_service.remove_region(user_id, 1)
        regions = settings_service.get_user_regions(user_id)
        assert regions == [2]


class TestCheckIfUserHasNoRegions:
    def test_no_regions(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        assert settings_service.check_if_user_has_no_regions(user_id) is True

    def test_with_regions(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.add_region(user_id, 1)
        assert settings_service.check_if_user_has_no_regions(user_id) is False


class TestGetGeoFolders:
    def test_get_folders(self, settings_service: DBClient):
        folders = settings_service.get_geo_folders()
        assert isinstance(folders, list)
        if folders:
            fid, name = folders[0]
            assert isinstance(fid, int)
            assert isinstance(name, str)


class TestGetAllUserPreferences:
    def test_no_preferences(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        prefs = settings_service.get_all_user_preferences(user_id)
        assert prefs == []

    def test_with_preferences(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_preference(user_id, 'new_searches')
        prefs = settings_service.get_all_user_preferences(user_id)
        assert 'new_searches' in prefs


class TestSavePreference:
    def test_save_preference(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_preference(user_id, 'new_searches')
        prefs = settings_service.get_all_user_preferences(user_id)
        assert 'new_searches' in prefs


class TestDeletePreferences:
    def test_delete_preferences(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_preference(user_id, 'new_searches')
        settings_service.save_preference(user_id, 'status_changes')
        settings_service.delete_preferences(user_id, ['new_searches'])
        prefs = settings_service.get_all_user_preferences(user_id)
        assert 'new_searches' not in prefs
        assert 'status_changes' in prefs


class TestPreferenceExists:
    def test_preference_exists(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_preference(user_id, 'new_searches')
        assert settings_service.preference_exists(user_id, ['new_searches']) is True

    def test_preference_not_exists(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        assert settings_service.preference_exists(user_id, ['new_searches']) is False


class TestSaveCoordinates:
    def test_save_coordinates(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_coordinates(user_id, 55.7558, 37.6173)
        coords = settings_service.get_coordinates(user_id)
        assert coords is not None
        lat, lon = coords
        assert float(lat) == pytest.approx(55.7558, rel=1e-4)
        assert float(lon) == pytest.approx(37.6173, rel=1e-4)

    def test_update_coordinates(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_coordinates(user_id, 55.7558, 37.6173)
        settings_service.save_coordinates(user_id, 59.9343, 30.3351)
        coords = settings_service.get_coordinates(user_id)
        assert coords is not None
        lat, lon = coords
        assert float(lat) == pytest.approx(59.9343, rel=1e-4)
        assert float(lon) == pytest.approx(30.3351, rel=1e-4)


class TestGetCoordinates:
    def test_no_coordinates(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        coords = settings_service.get_coordinates(user_id)
        assert coords is None

    def test_with_coordinates(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_coordinates(user_id, 55.7558, 37.6173)
        coords = settings_service.get_coordinates(user_id)
        assert coords is not None


class TestDeleteCoordinates:
    def test_delete_coordinates(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_coordinates(user_id, 55.7558, 37.6173)
        settings_service.delete_coordinates(user_id)
        coords = settings_service.get_coordinates(user_id)
        assert coords is None


class TestSaveRadius:
    def test_save_radius(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_radius(user_id, 150)
        radius = settings_service.get_radius(user_id)
        assert radius == 150

    def test_update_radius(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_radius(user_id, 150)
        settings_service.save_radius(user_id, 200)
        radius = settings_service.get_radius(user_id)
        assert radius == 200


class TestGetRadius:
    def test_no_radius(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        radius = settings_service.get_radius(user_id)
        assert radius is None

    def test_with_radius(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_radius(user_id, 150)
        radius = settings_service.get_radius(user_id)
        assert radius == 150


class TestDeleteRadius:
    def test_delete_radius(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_radius(user_id, 150)
        settings_service.delete_radius(user_id)
        radius = settings_service.get_radius(user_id)
        assert radius is None


class TestSaveAgePreference:
    def test_save_age_preference(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        period = AgePeriod(description='Дети', name='0-10', min_age=0, max_age=10, order=1)
        settings_service.save_age_preference(user_id, period)
        prefs = settings_service.get_age_preferences(user_id)
        assert (0, 10) in prefs


class TestDeleteAgePreference:
    def test_delete_age_preference(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        period = AgePeriod(description='Дети', name='0-10', min_age=0, max_age=10, order=1)
        settings_service.save_age_preference(user_id, period)
        settings_service.delete_age_preference(user_id, period)
        prefs = settings_service.get_age_preferences(user_id)
        assert (0, 10) not in prefs


class TestGetAgePreferences:
    def test_no_age_prefs(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        prefs = settings_service.get_age_preferences(user_id)
        assert prefs == []

    def test_with_age_prefs(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        period = AgePeriod(description='Дети', name='0-10', min_age=0, max_age=10, order=1)
        settings_service.save_age_preference(user_id, period)
        prefs = settings_service.get_age_preferences(user_id)
        assert (0, 10) in prefs


class TestSaveTopicType:
    def test_save_topic_type(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_topic_type(user_id, 0)
        types = settings_service.get_topic_types(user_id)
        assert 0 in types


class TestDeleteTopicType:
    def test_delete_topic_type(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_topic_type(user_id, 0)
        settings_service.delete_topic_type(user_id, 0)
        types = settings_service.get_topic_types(user_id)
        assert 0 not in types


class TestGetTopicTypes:
    def test_no_topic_types(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        types = settings_service.get_topic_types(user_id)
        assert types == []

    def test_with_topic_types(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_topic_type(user_id, 0)
        types = settings_service.get_topic_types(user_id)
        assert 0 in types


class TestSaveDefaultTopicTypes:
    def test_save_default_for_member(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_default_topic_types(user_id, 'member')
        types = settings_service.get_topic_types(user_id)
        assert 0 in types

    def test_save_default_for_new_member(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_default_topic_types(user_id, 'new_member')
        types = settings_service.get_topic_types(user_id)
        assert 0 in types


class TestGetSearchFollowMode:
    def test_no_mode(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        mode = settings_service.get_search_follow_mode(user_id)
        assert mode is False


class TestSetSearchFollowMode:
    def test_enable(self, settings_service: DBClient, user_id: int, session: Session):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.set_search_follow_mode(user_id, True)
        mode = settings_service.get_search_follow_mode(user_id)
        assert mode is True

    def test_disable(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.set_search_follow_mode(user_id, True)
        settings_service.set_search_follow_mode(user_id, False)
        mode = settings_service.get_search_follow_mode(user_id)
        assert mode is False


class TestRecordSearchWhiteness:
    def test_record_on(self, settings_service: DBClient, user_id: int, session: Session):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.record_search_whiteness(user_id, 12345, SearchFollowingMode.ON)
        # Verify by querying the whitelist table directly (different from search follow mode table)
        from sqlalchemy import text

        result = session.execute(
            text('SELECT search_following_mode FROM user_pref_search_whitelist WHERE user_id=:uid AND search_id=12345'),
            {'uid': user_id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == SearchFollowingMode.ON

    def test_record_off(self, settings_service: DBClient, user_id: int, session: Session):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.record_search_whiteness(user_id, 12345, SearchFollowingMode.OFF)
        from sqlalchemy import text

        result = session.execute(
            text('SELECT search_following_mode FROM user_pref_search_whitelist WHERE user_id=:uid AND search_id=12345'),
            {'uid': user_id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == SearchFollowingMode.OFF


class TestGetUserVkId:
    def test_no_vk_id(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id, vk_id=None)
        vk_id = settings_service.get_user_vk_id(user_id)
        assert vk_id is None

    def test_with_vk_id(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id, vk_id='test_vk_123')
        vk_id = settings_service.get_user_vk_id(user_id)
        assert vk_id == 'test_vk_123'


class TestSetUserVkId:
    def test_set_vk_id(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.set_user_vk_id(user_id, 'test_vk_456')
        vk_id = settings_service.get_user_vk_id(user_id)
        assert vk_id == 'test_vk_456'

    def test_update_vk_id(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id, vk_id='old_vk_id')
        settings_service.set_user_vk_id(user_id, 'new_vk_id')
        vk_id = settings_service.get_user_vk_id(user_id)
        assert vk_id == 'new_vk_id'


class TestGetUserByVkId:
    def test_find_by_vk_id(self, settings_service: DBClient, user_id: int, session: Session):
        unique_vk = f'findable_vk_{randint(1, 999999)}'
        db_factories.UserFactory.create_sync(user_id=user_id, vk_id=unique_vk)
        found_id = settings_service.get_user_by_vk_id(unique_vk)
        assert found_id == user_id

    def test_not_found(self, settings_service: DBClient):
        found_id = settings_service.get_user_by_vk_id('nonexistent_vk')
        assert found_id is None


class TestGetForumAttributes:
    def test_no_attributes(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        attrs = settings_service.get_forum_attributes(user_id)
        assert attrs is None

    def test_with_attributes(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        db_factories.UserForumAttributeFactory.create_sync(
            user_id=user_id,
            forum_username='test_user',
            forum_user_id=42,
            status='verified',
        )
        attrs = settings_service.get_forum_attributes(user_id)
        assert attrs is not None
        username, forum_id = attrs
        assert username == 'test_user'
        assert forum_id == 42


class TestVerifyForumAttributes:
    def test_verify_attributes(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        db_factories.UserForumAttributeFactory.create_sync(
            user_id=user_id,
            forum_username='test_user',
            forum_user_id=42,
            status=None,
        )
        settings_service.verify_forum_attributes(user_id)
        attrs = settings_service.get_forum_attributes(user_id)
        # After verification, the record should be marked verified
        # (the method updates the latest unverified record)
        assert attrs is not None
        username, forum_id = attrs
        assert username == 'test_user'
        assert forum_id == 42


class TestGetUserSysRoles:
    def test_no_roles(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        roles = settings_service.get_user_sys_roles(user_id)
        assert roles == []

    def test_with_roles(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.add_user_sys_role(user_id, 'tester')
        roles = settings_service.get_user_sys_roles(user_id)
        assert 'tester' in roles


class TestAddUserSysRole:
    def test_add_role(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.add_user_sys_role(user_id, 'admin')
        roles = settings_service.get_user_sys_roles(user_id)
        assert 'admin' in roles


class TestDeleteUserSysRole:
    def test_delete_role(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.add_user_sys_role(user_id, 'tester')
        settings_service.delete_user_sys_role(user_id, 'tester')
        roles = settings_service.get_user_sys_roles(user_id)
        assert 'tester' not in roles


class TestSaveUserMessage:
    def test_save_user_message(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_user_message(user_id, 'test message')
        # No return value to assert, just ensure no exception


class TestSaveBotReply:
    def test_save_bot_reply(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_bot_reply(user_id, 'test reply')
        # No return value to assert, just ensure no exception


class TestGetSettingsSummary:
    def test_no_settings(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        summary = settings_service.get_settings_summary(user_id)
        assert summary is not None
        assert summary.pref_notif_type is False

    def test_with_all_settings(self, settings_service: DBClient, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.save_preference(user_id, 'new_searches')
        # pref_region checks user_pref_region table (not user_regional_preferences)
        db_factories.UserPrefRegionFactory.create_sync(user_id=user_id, region_id=1)
        settings_service.save_coordinates(user_id, 55.7558, 37.6173)
        settings_service.save_radius(user_id, 150)
        summary = settings_service.get_settings_summary(user_id)
        assert summary is not None
        assert summary.pref_notif_type is True
        assert summary.pref_region is True
        assert summary.pref_coords is True
        assert summary.pref_radius is True
