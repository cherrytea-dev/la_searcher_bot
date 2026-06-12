"""Tests for the shared UserSettingsService module."""

from random import randint

import pytest
from sqlalchemy.orm import Session

from _dependencies.commons import SearchFollowingMode
from _dependencies.services.user_settings_service import (
    AgePeriod,
    UserSettingsService,
    get_user_settings_service,
)
from tests.common import fake, find_model
from tests.factories import db_factories, db_models


@pytest.fixture(scope='session')
def settings_service() -> UserSettingsService:
    return get_user_settings_service()


@pytest.fixture
def user_id() -> int:
    return randint(1, 1_000_000)


# =============================================================================
# Registration & Onboarding
# =============================================================================


class TestCheckIfNewUser:
    def test_new_user_returns_true(self, settings_service: UserSettingsService):
        user_id = fake.pyint()
        assert settings_service.check_if_new_user(user_id) is True

    def test_existing_user_returns_false(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        assert settings_service.check_if_new_user(user_id) is False


class TestGetOnboardingStep:
    def test_no_onboarding_step(self, settings_service: UserSettingsService, user_id: int):
        step_id, step_name = settings_service.get_onboarding_step(user_id)
        assert step_id == 99
        assert step_name is None

    def test_existing_onboarding_step(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserOnboardingFactory.create_sync(user_id=user_id, step_id=10, step_name='role_set')
        step_id, step_name = settings_service.get_onboarding_step(user_id)
        assert step_id == 10
        assert step_name == 'role_set'


class TestSaveUserRole:
    def test_save_member_role(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        role = settings_service.save_user_role(user_id, 'я состою в ЛизаАлерт')
        assert role == 'member'
        user = find_model(db_factories.get_session(), db_models.User, user_id=user_id)
        assert user is not None
        assert user.role == 'member'

    def test_save_new_member_role(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        role = settings_service.save_user_role(user_id, 'я хочу помогать ЛизаАлерт')
        assert role == 'new_member'
        user = find_model(db_factories.get_session(), db_models.User, user_id=user_id)
        assert user is not None
        assert user.role == 'new_member'

    def test_save_relative_role(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        role = settings_service.save_user_role(user_id, 'я ищу человека')
        assert role == 'relative'
        user = find_model(db_factories.get_session(), db_models.User, user_id=user_id)
        assert user is not None
        assert user.role == 'relative'

    def test_save_unknown_role(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        role = settings_service.save_user_role(user_id, 'some random role')
        assert role == 'unidentified'


class TestGetUserRole:
    def test_no_role(self, settings_service: UserSettingsService, user_id: int):
        role = settings_service.get_user_role(user_id)
        assert role is None

    def test_existing_role(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id, role='member')
        role = settings_service.get_user_role(user_id)
        assert role == 'member'


# =============================================================================
# Regions
# =============================================================================


class TestGetUserRegions:
    def test_no_regions(self, settings_service: UserSettingsService, user_id: int):
        regions = settings_service.get_user_regions(user_id)
        assert regions == []

    def test_with_regions(self, settings_service: UserSettingsService, user_id: int):
        region_ids = [101, 102, 103]
        for rid in region_ids:
            db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id, forum_folder_num=rid)
        regions = settings_service.get_user_regions(user_id)
        assert regions == region_ids


class TestAddRegion:
    def test_add_region(self, settings_service: UserSettingsService, user_id: int):
        settings_service.add_region(user_id, 42)
        saved = find_model(
            db_factories.get_session(),
            db_models.UserRegionalPreference,
            user_id=user_id,
            forum_folder_num=42,
        )
        assert saved is not None

    def test_add_duplicate_region(self, settings_service: UserSettingsService, user_id: int):
        settings_service.add_region(user_id, 42)
        # No unique constraint on (user_id, forum_folder_num), so duplicate insert succeeds
        settings_service.add_region(user_id, 42)


class TestRemoveRegion:
    def test_remove_region(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id, forum_folder_num=42)
        settings_service.remove_region(user_id, 42)
        saved = find_model(
            db_factories.get_session(),
            db_models.UserRegionalPreference,
            user_id=user_id,
            forum_folder_num=42,
        )
        assert saved is None

    def test_remove_nonexistent_region(self, settings_service: UserSettingsService, user_id: int):
        # Should not raise
        settings_service.remove_region(user_id, 999)


class TestCheckIfUserHasNoRegions:
    def test_no_regions(self, settings_service: UserSettingsService, user_id: int):
        assert settings_service.check_if_user_has_no_regions(user_id) is True

    def test_has_regions(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id)
        assert settings_service.check_if_user_has_no_regions(user_id) is False


class TestGetGeoFolders:
    def test_get_geo_folders(self, settings_service: UserSettingsService):
        folders = settings_service.get_geo_folders()
        assert isinstance(folders, list)


# =============================================================================
# Notification Preferences
# =============================================================================


class TestGetAllUserPreferences:
    def test_no_preferences(self, settings_service: UserSettingsService, user_id: int):
        prefs = settings_service.get_all_user_preferences(user_id)
        assert prefs == []

    def test_with_preferences(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserPreferenceFactory.create_sync(user_id=user_id, preference='topic_new', pref_id=0)
        db_factories.UserPreferenceFactory.create_sync(user_id=user_id, preference='status_change', pref_id=1)
        prefs = settings_service.get_all_user_preferences(user_id)
        assert 'topic_new' in prefs
        assert 'status_change' in prefs


class TestSavePreference:
    def test_save_preference(self, settings_service: UserSettingsService, user_id: int):
        settings_service.save_preference(user_id, 'topic_new')
        saved = find_model(
            db_factories.get_session(),
            db_models.UserPreference,
            user_id=user_id,
            preference='topic_new',
        )
        assert saved is not None


class TestDeletePreferences:
    def test_delete_preferences(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserPreferenceFactory.create_sync(user_id=user_id, preference='topic_new', pref_id=0)
        settings_service.delete_preferences(user_id, ['topic_new'])
        saved = find_model(
            db_factories.get_session(),
            db_models.UserPreference,
            user_id=user_id,
            preference='topic_new',
        )
        assert saved is None


class TestPreferenceExists:
    def test_preference_exists(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserPreferenceFactory.create_sync(user_id=user_id, preference='topic_new', pref_id=0)
        assert settings_service.preference_exists(user_id, ['topic_new']) is True

    def test_preference_not_exists(self, settings_service: UserSettingsService, user_id: int):
        assert settings_service.preference_exists(user_id, ['topic_new']) is False


# =============================================================================
# Coordinates
# =============================================================================


class TestSaveCoordinates:
    def test_save_coordinates(self, settings_service: UserSettingsService, user_id: int):
        settings_service.save_coordinates(user_id, 55.7558, 37.6173)
        saved = find_model(db_factories.get_session(), db_models.UserCoordinate, user_id=user_id)
        assert saved is not None
        assert float(saved.latitude) == 55.7558
        assert float(saved.longitude) == 37.6173

    def test_update_coordinates(self, settings_service: UserSettingsService, user_id: int):
        settings_service.save_coordinates(user_id, 55.7558, 37.6173)
        settings_service.save_coordinates(user_id, 59.9343, 30.3351)
        saved = find_model(db_factories.get_session(), db_models.UserCoordinate, user_id=user_id)
        assert float(saved.latitude) == 59.9343
        assert float(saved.longitude) == 30.3351


class TestGetCoordinates:
    def test_no_coordinates(self, settings_service: UserSettingsService, user_id: int):
        coords = settings_service.get_coordinates(user_id)
        assert coords is None

    def test_with_coordinates(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserCoordinateFactory.create_sync(user_id=user_id, latitude='55.7558', longitude='37.6173')
        coords = settings_service.get_coordinates(user_id)
        assert coords is not None
        assert coords[0] == '55.7558'
        assert coords[1] == '37.6173'


class TestDeleteCoordinates:
    def test_delete_coordinates(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserCoordinateFactory.create_sync(user_id=user_id)
        settings_service.delete_coordinates(user_id)
        saved = find_model(db_factories.get_session(), db_models.UserCoordinate, user_id=user_id)
        assert saved is None


# =============================================================================
# Radius
# =============================================================================


class TestSaveRadius:
    def test_save_radius(self, settings_service: UserSettingsService, user_id: int):
        settings_service.save_radius(user_id, 50)
        saved = find_model(db_factories.get_session(), db_models.UserPrefRadiu, user_id=user_id)
        assert saved is not None
        assert saved.radius == 50

    def test_update_radius(self, settings_service: UserSettingsService, user_id: int):
        settings_service.save_radius(user_id, 50)
        settings_service.save_radius(user_id, 100)
        saved = find_model(db_factories.get_session(), db_models.UserPrefRadiu, user_id=user_id)
        assert saved.radius == 100


class TestGetRadius:
    def test_no_radius(self, settings_service: UserSettingsService, user_id: int):
        radius = settings_service.get_radius(user_id)
        assert radius is None

    def test_with_radius(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserPrefRadiusFactory.create_sync(user_id=user_id, radius=75)
        radius = settings_service.get_radius(user_id)
        assert radius == 75


class TestDeleteRadius:
    def test_delete_radius(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserPrefRadiusFactory.create_sync(user_id=user_id)
        settings_service.delete_radius(user_id)
        saved = find_model(db_factories.get_session(), db_models.UserPrefRadiu, user_id=user_id)
        assert saved is None


# =============================================================================
# Age Preferences
# =============================================================================


class TestSaveAgePreference:
    def test_save_age_preference(self, settings_service: UserSettingsService, user_id: int):
        period = AgePeriod(description='test', name='test_name', min_age=18, max_age=30, order=1)
        settings_service.save_age_preference(user_id, period)
        saved = find_model(
            db_factories.get_session(),
            db_models.UserPrefAge,
            user_id=user_id,
            period_name=period.name,
        )
        assert saved is not None


class TestDeleteAgePreference:
    def test_delete_age_preference(self, settings_service: UserSettingsService, user_id: int):
        period = AgePeriod(description='test', name='test_name', min_age=18, max_age=30, order=1)
        db_factories.UserPrefAgeFactory.create_sync(
            user_id=user_id,
            period_name=period.name,
            period_min=period.min_age,
            period_max=period.max_age,
        )
        settings_service.delete_age_preference(user_id, period)
        saved = find_model(
            db_factories.get_session(),
            db_models.UserPrefAge,
            user_id=user_id,
            period_name=period.name,
        )
        assert saved is None


class TestGetAgePreferences:
    def test_no_age_prefs(self, settings_service: UserSettingsService, user_id: int):
        prefs = settings_service.get_age_preferences(user_id)
        assert prefs == []

    def test_with_age_prefs(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserPrefAgeFactory.create_sync(user_id=user_id, period_min=18, period_max=30)
        db_factories.UserPrefAgeFactory.create_sync(user_id=user_id, period_min=31, period_max=50)
        prefs = settings_service.get_age_preferences(user_id)
        assert (18, 30) in prefs
        assert (31, 50) in prefs


# =============================================================================
# Topic Types
# =============================================================================


class TestSaveTopicType:
    def test_save_topic_type(self, settings_service: UserSettingsService, user_id: int):
        settings_service.save_topic_type(user_id, 1)
        saved = find_model(
            db_factories.get_session(),
            db_models.UserPrefTopicType,
            user_id=user_id,
            topic_type_id=1,
        )
        assert saved is not None


class TestDeleteTopicType:
    def test_delete_topic_type(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserPrefTopicTypeFactory.create_sync(user_id=user_id, topic_type_id=1)
        settings_service.delete_topic_type(user_id, 1)
        saved = find_model(
            db_factories.get_session(),
            db_models.UserPrefTopicType,
            user_id=user_id,
            topic_type_id=1,
        )
        assert saved is None


class TestGetTopicTypes:
    def test_no_topic_types(self, settings_service: UserSettingsService, user_id: int):
        types = settings_service.get_topic_types(user_id)
        assert types == []

    def test_with_topic_types(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserPrefTopicTypeFactory.create_sync(user_id=user_id, topic_type_id=1)
        db_factories.UserPrefTopicTypeFactory.create_sync(user_id=user_id, topic_type_id=2)
        types = settings_service.get_topic_types(user_id)
        assert 1 in types
        assert 2 in types


class TestSaveDefaultTopicTypes:
    def test_save_default_for_member(self, settings_service: UserSettingsService, user_id: int):
        settings_service.save_default_topic_types(user_id, user_role='member')
        types = settings_service.get_topic_types(user_id)
        assert 0 in types  # default topic type for members

    def test_save_default_for_new_member(self, settings_service: UserSettingsService, user_id: int):
        settings_service.save_default_topic_types(user_id, user_role='new_member')
        types = settings_service.get_topic_types(user_id)
        assert 0 in types


# =============================================================================
# Search Following
# =============================================================================


class TestGetSearchFollowMode:
    def test_not_set(self, settings_service: UserSettingsService, user_id: int):
        assert settings_service.get_search_follow_mode(user_id) is False

    def test_enabled(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserPrefSearchFilteringFactory.create_sync(user_id=user_id, filter_name=['whitelist'])
        assert settings_service.get_search_follow_mode(user_id) is True


class TestSetSearchFollowMode:
    def test_enable(self, settings_service: UserSettingsService, user_id: int, session: Session):
        user = db_models.User(user_id=user_id, role='new_member')
        session.add(user)
        session.commit()
        settings_service.set_search_follow_mode(user_id, True)
        saved = find_model(
            db_factories.get_session(),
            db_factories.db_models.t_user_pref_search_filtering,
            user_id=user_id,
        )
        assert saved is not None
        assert saved.filter_name == ['whitelist']

    def test_disable(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        db_factories.UserPrefSearchFilteringFactory.create_sync(user_id=user_id, filter_name=['whitelist'])
        settings_service.set_search_follow_mode(user_id, False)
        saved = find_model(
            db_factories.get_session(),
            db_factories.db_models.t_user_pref_search_filtering,
            user_id=user_id,
        )
        assert saved is None or saved.filter_name == ['']


class TestRecordSearchWhiteness:
    def test_record_on(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        search_id = fake.pyint()
        settings_service.record_search_whiteness(user_id, search_id, SearchFollowingMode.ON)
        saved = find_model(
            db_factories.get_session(),
            db_models.UserPrefSearchWhitelist,
            user_id=user_id,
            search_id=search_id,
        )
        assert saved is not None
        assert saved.search_following_mode == SearchFollowingMode.ON

    def test_record_off(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        search_id = fake.pyint()
        settings_service.record_search_whiteness(user_id, search_id, SearchFollowingMode.OFF)
        saved = find_model(
            db_factories.get_session(),
            db_models.UserPrefSearchWhitelist,
            user_id=user_id,
            search_id=search_id,
        )
        assert saved is not None
        assert saved.search_following_mode == SearchFollowingMode.OFF


# =============================================================================
# VK ID Linking
# =============================================================================


class TestGetUserVkId:
    def test_no_vk_id(self, settings_service: UserSettingsService, user_id: int):
        vk_id = settings_service.get_user_vk_id(user_id)
        assert vk_id is None

    def test_with_vk_id(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id, vk_id='12345')
        vk_id = settings_service.get_user_vk_id(user_id)
        assert vk_id == '12345'


class TestSetUserVkId:
    def test_set_vk_id(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        settings_service.set_user_vk_id(user_id, '67890')
        user = find_model(db_factories.get_session(), db_models.User, user_id=user_id)
        assert user is not None
        assert user.vk_id == '67890'

    def test_update_vk_id(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id, vk_id='12345')
        settings_service.set_user_vk_id(user_id, '67890')
        user = find_model(db_factories.get_session(), db_models.User, user_id=user_id)
        assert user.vk_id == '67890'


class TestGetUserByVkId:
    def test_find_by_vk_id(self, settings_service: UserSettingsService, user_id: int, session: Session):
        vk_id = str(user_id)
        user = db_models.User(user_id=user_id, vk_id=vk_id, role='new_member')
        session.add(user)
        session.commit()
        found = settings_service.get_user_by_vk_id(int(vk_id))
        assert found == user_id

    def test_not_found(self, settings_service: UserSettingsService):
        user_id = randint(0, 1000**3)
        found = settings_service.get_user_by_vk_id(user_id)
        assert found is None


# =============================================================================
# Forum Attributes
# =============================================================================


class TestGetForumAttributes:
    def test_no_attributes(self, settings_service: UserSettingsService, user_id: int):
        attrs = settings_service.get_forum_attributes(user_id)
        assert attrs is None

    def test_with_attributes(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserForumAttributeFactory.create_sync(
            user_id=user_id, forum_username='test_user', forum_user_id=42, status='verified'
        )
        attrs = settings_service.get_forum_attributes(user_id)
        assert attrs is not None
        assert attrs[0] == 'test_user'
        assert attrs[1] == 42


class TestVerifyForumAttributes:
    def test_verify_attributes(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserForumAttributeFactory.create_sync(user_id=user_id, status='pending')
        settings_service.verify_forum_attributes(user_id)
        saved = find_model(
            db_factories.get_session(),
            db_models.UserForumAttribute,
            user_id=user_id,
        )
        assert saved is not None
        assert saved.status == 'verified'


# =============================================================================
# System Roles
# =============================================================================


class TestGetUserSysRoles:
    def test_no_roles(self, settings_service: UserSettingsService, user_id: int):
        roles = settings_service.get_user_sys_roles(user_id)
        assert roles == []

    def test_with_roles(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserRoleFactory.create_sync(user_id=user_id, role='admin')
        db_factories.UserRoleFactory.create_sync(user_id=user_id, role='tester')
        roles = settings_service.get_user_sys_roles(user_id)
        assert 'admin' in roles
        assert 'tester' in roles


class TestAddUserSysRole:
    def test_add_role(self, settings_service: UserSettingsService, user_id: int):
        settings_service.add_user_sys_role(user_id, 'tester')
        saved = find_model(
            db_factories.get_session(),
            db_models.UserRole,
            user_id=user_id,
            role='tester',
        )
        assert saved is not None


class TestDeleteUserSysRole:
    def test_delete_role(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserRoleFactory.create_sync(user_id=user_id, role='tester')
        settings_service.delete_user_sys_role(user_id, 'tester')
        saved = find_model(
            db_factories.get_session(),
            db_models.UserRole,
            user_id=user_id,
            role='tester',
        )
        assert saved is None


# =============================================================================
# Dialog History
# =============================================================================


class TestSaveUserMessage:
    def test_save_user_message(self, settings_service: UserSettingsService, user_id: int):
        text = fake.text()
        settings_service.save_user_message(user_id, text)
        saved = find_model(
            db_factories.get_session(),
            db_models.Dialog,
            user_id=user_id,
            author='user',
            message_text=text,
        )
        assert saved is not None


class TestSaveBotReply:
    def test_save_bot_reply(self, settings_service: UserSettingsService, user_id: int):
        text = fake.text()
        settings_service.save_bot_reply(user_id, text)
        saved = find_model(
            db_factories.get_session(),
            db_models.Dialog,
            user_id=user_id,
            author='bot',
            message_text=text,
        )
        assert saved is not None


# =============================================================================
# Settings Summary
# =============================================================================


class TestGetSettingsSummary:
    def test_no_settings(self, settings_service: UserSettingsService, user_id: int):
        summary = settings_service.get_settings_summary(user_id)
        assert summary is None

    def test_with_all_settings(self, settings_service: UserSettingsService, user_id: int):
        db_factories.UserFactory.create_sync(user_id=user_id)
        db_factories.UserPrefAgeFactory.create_sync(user_id=user_id)
        db_factories.UserCoordinateFactory.create_sync(user_id=user_id)
        db_factories.UserPrefRadiusFactory.create_sync(user_id=user_id)
        db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id)
        db_factories.UserPrefTopicTypeFactory.create_sync(user_id=user_id)

        summary = settings_service.get_settings_summary(user_id)
        assert summary is not None
        assert summary.user_id == user_id


# =============================================================================
# Singleton
# =============================================================================


def test_get_user_settings_service_is_singleton():
    """Test that get_user_settings_service returns the same instance."""
    svc1 = get_user_settings_service()
    svc2 = get_user_settings_service()
    assert svc1 is svc2
