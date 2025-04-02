from unittest.mock import MagicMock, Mock

import pytest
from faker import Faker
from psycopg2.extensions import cursor

from _dependencies.commons import get_app_config, sql_connect_by_psycopg2
from communicate._utils import handlers
from communicate._utils.database import DBClient
from tests.common import find_model
from tests.factories import db_factories, db_models
from tests.factories.telegram import get_callback_query, get_reply_markup

fake = Faker()


@pytest.fixture(scope='session')
def db_client() -> DBClient:
    db = DBClient()
    with db.connect():
        yield db


@pytest.fixture
def user_id() -> int:
    return fake.pyint()


def test_save_user_message_to_bot(session, db_client: DBClient, user_id: int):
    message = fake.text()

    db_client.save_user_message_to_bot(user_id, message)

    assert find_model(session, db_models.Dialog, user_id=user_id, author='user', message_text=message)


def test_add_user_sys_role(session, db_client: DBClient, user_id: int):
    role = fake.pystr(1, 5)

    db_client.add_user_sys_role(user_id, role)

    assert find_model(session, db_models.UserRole, user_id=user_id, role=role)


def test_delete_user_sys_role(session, db_client: DBClient, user_id: int):
    role_model = db_factories.UserRoleFactory.create_sync(user_id=user_id)

    db_client.delete_user_sys_role(user_id, role_model.role)

    assert not find_model(session, db_models.UserRole, user_id=user_id, role=role_model.role)


def test_delete_user_coordinates(session, db_client: DBClient, user_id):
    db_factories.UserCoordinateFactory.create_sync(user_id=user_id)

    db_client.delete_user_coordinates(user_id)

    assert not find_model(session, db_models.UserCoordinate, user_id=user_id)


def test_get_saved_user_coordinates(session, db_client: DBClient, user_id: int):
    # Create a user coordinate using the factory
    coordinate = db_factories.UserCoordinateFactory.create_sync(user_id=user_id)

    # Call the method to get saved user coordinates
    saved_coordinates = db_client.get_saved_user_coordinates(user_id)

    # Assert that the returned coordinates match the created one
    assert saved_coordinates is not None
    assert len(saved_coordinates) == 2
    assert saved_coordinates[0] == str(coordinate.latitude)
    assert saved_coordinates[1] == str(coordinate.longitude)


def test_save_user_coordinates(session, db_client: DBClient, user_id: int):
    # Define test coordinates
    latitude = 55.7558
    longitude = 37.6173

    # Call the method to save user coordinates
    db_client.save_user_coordinates(user_id, latitude, longitude)

    # Retrieve the saved coordinates
    saved_coordinates = db_client.get_saved_user_coordinates(user_id)

    # Assert that the saved coordinates match the input
    assert saved_coordinates is not None
    assert saved_coordinates[0] == str(latitude)
    assert saved_coordinates[1] == str(longitude)


def test_check_if_user_has_no_regions(session, db_client: DBClient, user_id: int):
    # Ensure the user has no regions initially
    assert db_client.check_if_user_has_no_regions(user_id) is True

    # Add a region for the user
    db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id)

    # Check again, now the user should have at least one region
    assert db_client.check_if_user_has_no_regions(user_id) is False


def test_save_user_pref_role(session, db_client: DBClient, user_id: int):
    # Define a role description
    role_desc = 'я состою в ЛизаАлерт'

    # Call the method to save the user role
    saved_role = db_client.save_user_pref_role(user_id, role_desc)

    # Retrieve the saved role from the database
    user = find_model(session, db_models.User, user_id=user_id)

    # Assert that the saved role matches the expected role
    assert saved_role == 'member'
    assert user is not None
    assert user.role == 'member'


def test_save_user_pref_topic_type(session, db_client: DBClient, user_id: int):
    # Define a topic type ID
    topic_type_id = 3

    # Call the method to save the user topic type preference
    db_client._save_user_pref_topic_type(user_id, topic_type_id)

    # Retrieve the saved topic type from the database
    saved_topic_type = find_model(session, db_models.UserPrefTopicType, user_id=user_id, topic_type_id=topic_type_id)

    # Assert that the saved topic type matches the input
    assert saved_topic_type is not None
    assert saved_topic_type.topic_type_id == topic_type_id


def test_get_user_regions_from_db(session, db_client: DBClient, user_id: int):
    # Add regions for the user
    region_ids = [101, 102, 103]
    for region_id in region_ids:
        db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id, forum_folder_num=region_id)

    # Call the method to get user regions
    user_regions = db_client.get_user_regions_from_db(user_id)

    # Assert that the returned regions match the created ones
    assert user_regions == region_ids


def test_get_geo_folders_db(session, db_client: DBClient):
    # Add geo folders to the database
    geo_folders = [
        (1, 'Searches Folder 1'),
        (2, 'Searches Folder 2'),
    ]
    for folder_id, folder_name in geo_folders:
        db_factories.GeoFolderFactory.create_sync(folder_id=folder_id, folder_display_name=folder_name)

    # Call the method to get geo folders
    retrieved_folders = db_client.get_geo_folders_db()

    # Assert that the returned folders match the created ones
    assert retrieved_folders == geo_folders


def test_check_if_new_user(session, db_client: DBClient, user_id: int):
    # Initially, the user should be new
    assert db_client.check_if_new_user(user_id) is True

    # Add the user to the database
    db_factories.UserFactory.create_sync(user_id=user_id)

    # Now the user should not be new
    assert db_client.check_if_new_user(user_id) is False


def test_save_user_pref_urgency(session, db_client: DBClient, user_id: int):
    # Define urgency values
    urgency_value = 'high'
    b_pref_urgency_highest = 'highest'
    b_pref_urgency_high = 'high'
    b_pref_urgency_medium = 'medium'
    b_pref_urgency_low = 'low'

    # Call the method to save user urgency preference
    db_client.save_user_pref_urgency(
        user_id,
        urgency_value,
        b_pref_urgency_highest,
        b_pref_urgency_high,
        b_pref_urgency_medium,
        b_pref_urgency_low,
    )

    # Retrieve the saved urgency preference
    saved_urgency = find_model(session, db_models.UserPrefUrgency, user_id=user_id)

    # Assert that the saved urgency matches the input
    assert saved_urgency is not None
    assert saved_urgency.pref_name == urgency_value


def test_get_user_reg_folders_preferences(session, db_client: DBClient, user_id: int):
    # Add regional preferences for the user
    region_ids = [201, 202, 203]
    for region_id in region_ids:
        db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id, forum_folder_num=region_id)

    # Call the method to get user regional folder preferences
    user_preferences = db_client.get_user_reg_folders_preferences(user_id)

    # Assert that the returned preferences match the created ones
    assert user_preferences == region_ids


def test_user_preference_save(session, db_client: DBClient, user_id: int):
    # Define a preference key and value
    pref_key = 'theme'
    pref_value = 'dark'

    # Call the method to save the user preference
    db_client.user_preference_save(user_id, pref_key, pref_value)

    # Retrieve the saved preference using the find_model function
    saved_preference = find_model(session, db_models.UserPreference, user_id=user_id, pref_key=pref_key)

    # Assert that the saved preference matches the input
    assert saved_preference is not None
    assert saved_preference.pref_value == pref_value


def test_user_preference_delete(session, db_client: DBClient, user_id: int):
    # Define a preference key and value
    pref_key = 'theme'
    pref_value = 'dark'

    # Save the preference first
    db_factories.UserPreferenceFactory.create_sync(user_id=user_id, pref_key=pref_key, pref_value=pref_value)

    # Call the method to delete the user preference
    db_client.user_preference_delete(user_id, pref_key)

    # Assert that the preference no longer exists
    deleted_preference = find_model(session, db_models.UserPreference, user_id=user_id, pref_key=pref_key)
    assert deleted_preference is None


def test_user_preference_is_exists(session, db_client: DBClient, user_id: int):
    # Define a preference key and value
    pref_key = 'theme'
    pref_value = 'dark'

    # Initially, the preference should not exist
    assert db_client.user_preference_is_exists(user_id, pref_key) is False

    # Save the preference
    db_factories.UserPreferenceFactory.create_sync(user_id=user_id, pref_key=pref_key, pref_value=pref_value)

    # Now the preference should exist
    assert db_client.user_preference_is_exists(user_id, pref_key) is True


def test_get_last_bot_msg(session, db_client: DBClient, user_id: int):
    # Define a bot message
    message_id = 12345
    db_factories.BotMessageFactory.create_sync(user_id=user_id, message_id=message_id)

    # Call the method to get the last bot message
    last_bot_msg = db_client.get_last_bot_msg(user_id)

    # Assert that the returned message matches the created one
    assert last_bot_msg == message_id


def test_get_user_forum_attributes_db(session, db_client: DBClient, user_id: int):
    # Define forum attributes
    forum_nickname = 'test_user'
    forum_id = 56789
    db_factories.UserForumAttributesFactory.create_sync(
        user_id=user_id, forum_nickname=forum_nickname, forum_id=forum_id
    )

    # Call the method to get user forum attributes
    forum_attributes = db_client.get_user_forum_attributes_db(user_id)

    # Assert that the returned attributes match the created ones
    assert forum_attributes is not None
    assert forum_attributes['forum_nickname'] == forum_nickname
    assert forum_attributes['forum_id'] == forum_id


def test_check_onboarding_step(session, db_client: DBClient, user_id: int):
    # Add an onboarding step for the user
    step_id = 10
    step_name = 'role_set'
    db_factories.UserOnboardingFactory.create_sync(user_id=user_id, step_id=step_id, step_name=step_name)

    # Call the method to check the onboarding step
    step_id_result, step_name_result = db_client.check_onboarding_step(user_id, user_is_new=False)

    # Assert that the returned step matches the created one
    assert step_id_result == step_id
    assert step_name_result == step_name


def test_save_bot_reply_to_user(session, db_client: DBClient, user_id: int):
    # Define a bot reply message
    message_id = 12345
    message_text = 'Hello, user!'

    # Call the method to save the bot reply
    db_client.save_bot_reply_to_user(user_id, message_id, message_text)

    # Retrieve the saved bot reply
    saved_reply = find_model(session, db_models.Dialog, user_id=user_id, author='bot', message_text=message_text)

    # Assert that the saved reply matches the input
    assert saved_reply is not None
    assert saved_reply.message_id == message_id
    assert saved_reply.message_text == message_text


def test_save_last_user_message_in_db(session, db_client: DBClient, user_id: int):
    # Define a user message
    message_text = 'This is my last message.'

    # Call the method to save the last user message
    db_client.save_last_user_message_in_db(user_id, message_text)

    # Retrieve the saved user message
    saved_message = find_model(session, db_models.Dialog, user_id=user_id, author='user', message_text=message_text)

    # Assert that the saved message matches the input
    assert saved_message is not None
    assert saved_message.message_text == message_text


def test_set_search_follow_mode(session, db_client: DBClient, user_id: int):
    # Set the search follow mode for the user
    follow_mode = True
    db_client.set_search_follow_mode(user_id, follow_mode)

    # Retrieve the saved follow mode
    saved_follow_mode = find_model(session, db_models.UserPreference, user_id=user_id, pref_key='search_follow_mode')

    # Assert that the saved follow mode matches the input
    assert saved_follow_mode is not None
    assert saved_follow_mode.pref_value == str(follow_mode)


def test_delete_folder_from_user_regional_preference(session, db_client: DBClient, user_id: int):
    # Add a regional preference for the user
    folder_id = 101
    db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id, forum_folder_num=folder_id)

    # Call the method to delete the folder from user regional preferences
    db_client.delete_folder_from_user_regional_preference(user_id, folder_id)

    # Assert that the folder no longer exists in the user's regional preferences
    deleted_folder = find_model(session, db_models.UserRegionalPreference, user_id=user_id, forum_folder_num=folder_id)
    assert deleted_folder is None


def test_get_folders_with_followed_searches(session, db_client: DBClient, user_id: int):
    # Add followed searches for the user
    folder_ids = [101, 102, 103]
    for folder_id in folder_ids:
        db_factories.SearchFactory.create_sync(forum_folder_id=folder_id)
        db_factories.UserPrefSearchWhitelistFactory.create_sync(
            user_id=user_id, search_id=folder_id, search_following_mode=True
        )

    # Call the method to get folders with followed searches
    followed_folders = db_client.get_folders_with_followed_searches(user_id)

    # Assert that the returned folders match the created ones
    assert followed_folders == [(folder_id,) for folder_id in folder_ids]


def test_add_folder_to_user_regional_preference(session, db_client: DBClient, user_id: int):
    # Define a folder ID
    folder_id = 201

    # Call the method to add the folder to user regional preferences
    db_client.add_folder_to_user_regional_preference(user_id, folder_id)

    # Retrieve the added folder
    added_folder = find_model(session, db_models.UserRegionalPreference, user_id=user_id, forum_folder_num=folder_id)

    # Assert that the folder was added successfully
    assert added_folder is not None
    assert added_folder.forum_folder_num == folder_id


def test_get_user_regions(session, db_client: DBClient, user_id: int):
    # Add regions for the user
    region_ids = [301, 302, 303]
    for region_id in region_ids:
        db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id, forum_folder_num=region_id)

    # Call the method to get user regions
    user_regions = db_client.get_user_regions(user_id)

    # Assert that the returned regions match the created ones
    assert user_regions == region_ids


def test_check_saved_radius(session, db_client: DBClient, user_id: int):
    # Save a radius for the user
    radius = 50
    db_factories.UserRadiusFactory.create_sync(user_id=user_id, radius=radius)

    # Call the method to check the saved radius
    saved_radius = db_client.check_saved_radius(user_id)

    # Assert that the saved radius matches the created one
    assert saved_radius == radius


def test_delete_user_saved_radius(session, db_client: DBClient, user_id: int):
    # Save a radius for the user
    radius = 50
    db_factories.UserRadiusFactory.create_sync(user_id=user_id, radius=radius)

    # Call the method to delete the user's saved radius
    db_client.delete_user_saved_radius(user_id)

    # Assert that the radius no longer exists
    deleted_radius = find_model(session, db_models.UserRadius, user_id=user_id)
    assert deleted_radius is None


def test_save_user_radius(session, db_client: DBClient, user_id: int):
    # Define a radius value
    radius = 100

    # Call the method to save the user's radius
    db_client.save_user_radius(user_id, radius)

    # Retrieve the saved radius
    saved_radius = find_model(session, db_models.UserRadius, user_id=user_id)

    # Assert that the saved radius matches the input
    assert saved_radius is not None
    assert saved_radius.radius == radius


def test_delete_user_saved_topic_type(session, db_client: DBClient, user_id: int):
    # Add a topic type for the user
    topic_type_id = 1
    db_factories.UserPrefTopicTypeFactory.create_sync(user_id=user_id, topic_type_id=topic_type_id)

    # Call the method to delete the topic type
    db_client.delete_user_saved_topic_type(user_id, topic_type_id)

    # Assert that the topic type no longer exists
    deleted_topic_type = find_model(session, db_models.UserPrefTopicType, user_id=user_id, topic_type_id=topic_type_id)
    assert deleted_topic_type is None


def test_record_topic_type(session, db_client: DBClient, user_id: int):
    # Define a topic type ID
    topic_type_id = 2

    # Call the method to record the topic type
    db_client.record_topic_type(user_id, topic_type_id)

    # Retrieve the recorded topic type
    recorded_topic_type = find_model(session, db_models.UserPrefTopicType, user_id=user_id, topic_type_id=topic_type_id)

    # Assert that the topic type was recorded successfully
    assert recorded_topic_type is not None
    assert recorded_topic_type.topic_type_id == topic_type_id


def test_check_saved_topic_types(session, db_client: DBClient, user_id: int):
    # Add topic types for the user
    topic_type_ids = [1, 2, 3]
    for topic_type_id in topic_type_ids:
        db_factories.UserPrefTopicTypeFactory.create_sync(user_id=user_id, topic_type_id=topic_type_id)

    # Call the method to check saved topic types
    saved_topic_types = db_client.check_saved_topic_types(user_id)

    # Assert that the returned topic types match the created ones
    assert saved_topic_types == topic_type_ids


def test_record_search_whiteness(session, db_client: DBClient, user_id: int):
    # Define search parameters
    search_id = 101
    search_following_mode = True

    # Call the method to record search whiteness
    db_client.record_search_whiteness(user_id, search_id, search_following_mode)

    # Retrieve the recorded search whiteness
    recorded_whiteness = find_model(session, db_models.UserPrefSearchWhitelist, user_id=user_id, search_id=search_id)

    # Assert that the search whiteness was recorded successfully
    assert recorded_whiteness is not None
    assert recorded_whiteness.search_following_mode == search_following_mode


def test_add_region_to_user_settings(session, db_client: DBClient, user_id: int):
    # Define a region ID
    region_id = 301

    # Call the method to add the region to user settings
    db_client.add_region_to_user_settings(user_id, region_id)

    # Retrieve the added region
    added_region = find_model(session, db_models.UserRegionalPreference, user_id=user_id, forum_folder_num=region_id)

    # Assert that the region was added successfully
    assert added_region is not None
    assert added_region.forum_folder_num == region_id


def test_save_user_age_prefs(session, db_client: DBClient, user_id: int):
    # Define an age preference
    age_pref = '18-25'

    # Call the method to save the user's age preference
    db_client.save_user_age_prefs(user_id, age_pref)

    # Retrieve the saved age preference
    saved_age_pref = find_model(session, db_models.UserAgePreference, user_id=user_id, age_pref=age_pref)

    # Assert that the age preference was saved successfully
    assert saved_age_pref is not None
    assert saved_age_pref.age_pref == age_pref


def test_delete_user_age_pref(session, db_client: DBClient, user_id: int):
    # Add an age preference for the user
    age_pref = '18-25'
    db_factories.UserAgePreferenceFactory.create_sync(user_id=user_id, age_pref=age_pref)

    # Call the method to delete the user's age preference
    db_client.delete_user_age_pref(user_id, age_pref)

    # Assert that the age preference no longer exists
    deleted_age_pref = find_model(session, db_models.UserAgePreference, user_id=user_id, age_pref=age_pref)
    assert deleted_age_pref is None


def test_get_age_prefs(session, db_client: DBClient, user_id: int):
    # Add age preferences for the user
    age_prefs = ['18-25', '26-35', '36-45']
    for age_pref in age_prefs:
        db_factories.UserAgePreferenceFactory.create_sync(user_id=user_id, age_pref=age_pref)

    # Call the method to get age preferences
    retrieved_age_prefs = db_client.get_age_prefs(user_id)

    # Assert that the retrieved age preferences match the created ones
    assert retrieved_age_prefs == [(age_pref,) for age_pref in age_prefs]


def test_get_existing_user_settings(session, db_client: DBClient, user_id: int):
    # Add user settings to the database
    db_factories.UserFactory.create_sync(user_id=user_id)
    db_factories.UserAgePreferenceFactory.create_sync(user_id=user_id)
    db_factories.UserCoordinateFactory.create_sync(user_id=user_id)
    db_factories.UserRadiusFactory.create_sync(user_id=user_id)
    db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id)
    db_factories.UserPrefTopicTypeFactory.create_sync(user_id=user_id)

    # Call the method to get existing user settings
    user_settings = db_client.get_existing_user_settings(user_id)

    # Assert that the returned settings are correct
    assert user_settings is not None
    assert user_settings[0] is True  # Role exists
    assert user_settings[1] is True  # Age preference exists
    assert user_settings[2] is True  # Coordinates exist
    assert user_settings[3] is True  # Radius exists
    assert user_settings[4] is True  # Regional preferences exist
    assert user_settings[5] is True  # Topic type preferences exist


def test_get_all_user_preferences(session, db_client: DBClient, user_id: int):
    # Add user preferences to the database
    preferences = ['theme:dark', 'notifications:on', 'language:en']
    for pref in preferences:
        db_factories.UserPreferenceFactory.create_sync(
            user_id=user_id, pref_key=pref.split(':')[0], pref_value=pref.split(':')[1]
        )

    # Call the method to get all user preferences
    user_preferences = db_client.get_all_user_preferences(user_id)

    # Assert that the returned preferences match the created ones
    assert user_preferences == [(pref,) for pref in preferences]


def test_get_all_active_searches_in_one_region_2(session, db_client: DBClient, user_id: int):
    # Add active searches for a region
    region_id = 101
    searches = [
        db_factories.SearchFactory.create_sync(forum_folder_id=region_id, status='Ищем'),
        db_factories.SearchFactory.create_sync(forum_folder_id=region_id, status='Возобновлен'),
    ]

    # Call the method to get all active searches in the region
    active_searches = db_client.get_all_active_searches_in_one_region_2(region_id, user_id)

    # Assert that the returned searches match the created ones
    assert len(active_searches) == len(searches)
    for search in searches:
        assert any(search.search_forum_num == active[0] for active in active_searches)


def test_get_all_searches_in_one_region(session, db_client: DBClient):
    # Add searches for a region
    region_id = 102
    searches = [
        db_factories.SearchFactory.create_sync(forum_folder_id=region_id),
        db_factories.SearchFactory.create_sync(forum_folder_id=region_id),
    ]

    # Call the method to get all searches in the region
    all_searches = db_client.get_all_searches_in_one_region(region_id)

    # Assert that the returned searches match the created ones
    assert len(all_searches) == len(searches)
    for search in searches:
        assert any(search.search_forum_num == all_search[0] for all_search in all_searches)


def test_get_all_last_searches_in_region(session, db_client: DBClient, user_id: int):
    # Add searches for a region
    region_id = 103
    searches = [
        db_factories.SearchFactory.create_sync(forum_folder_id=region_id),
        db_factories.SearchFactory.create_sync(forum_folder_id=region_id),
    ]

    # Call the method to get all last searches in the region
    last_searches = db_client.get_all_last_searches_in_region(region_id, user_id, only_followed=False)

    # Assert that the returned searches match the created ones
    assert len(last_searches) == len(searches)
    for search in searches:
        assert any(search.search_forum_num == last_search[0] for last_search in last_searches)


def test_get_active_searches_in_one_region(session, db_client: DBClient):
    # Add active searches for a region
    region_id = 104
    searches = [
        db_factories.SearchFactory.create_sync(forum_folder_id=region_id, status='Ищем'),
        db_factories.SearchFactory.create_sync(forum_folder_id=region_id, status='Возобновлен'),
    ]

    # Call the method to get active searches in the region
    active_searches = db_client.get_active_searches_in_one_region(region_id)

    # Assert that the returned searches match the created ones
    assert len(active_searches) == len(searches)
    for search in searches:
        assert any(search.search_forum_num == active[0] for active in active_searches)
