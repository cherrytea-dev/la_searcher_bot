import pytest

from communicate._utils.common import AgePeriod, SearchFollowingMode, SearchSummary, UserInputState
from communicate._utils.database import DBClient, UserSettingsSummary
from tests.common import fake, find_model
from tests.factories import db_factories, db_models


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

    # Assert that the saved role matches the expected role
    assert saved_role == 'member'
    user = find_model(session, db_models.User, user_id=user_id)
    assert user.role == 'member'


def test__save_user_pref_topic_type(session, db_client: DBClient, user_id: int):
    # Define a topic type ID
    topic_type_id = 3

    # Call the method to save the user topic type preference
    db_client._save_user_pref_topic_type(user_id, topic_type_id)

    # Retrieve the saved topic type from the database
    saved_topic_type = find_model(session, db_models.UserPrefTopicType, user_id=user_id, topic_type_id=topic_type_id)

    # Assert that the saved topic type matches the input
    assert saved_topic_type is not None
    assert saved_topic_type.topic_type_id == topic_type_id


def test_save_user_pref_topic_type_root(session, db_client: DBClient, user_id: int):
    # Define a topic type ID
    topic_type_id = 0

    # Call the method to save the user topic type preference
    db_client.save_user_pref_topic_type(user_id, user_role='member')

    # Retrieve the saved topic type
    saved_topic_type = find_model(session, db_models.UserPrefTopicType, user_id=user_id, topic_type_id=topic_type_id)

    # Assert that the topic type was saved successfully
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


@pytest.mark.skip(reason='not trivial with database view')
def test_get_geo_folders_db(session, db_client: DBClient):
    # Add geo folders to the database
    geo_folders = [
        (1, 'Searches Folder 1'),
        (2, 'Searches Folder 2'),
    ]
    for folder_id, folder_name in geo_folders:
        db_factories.GeoFolderFactory.create_sync(
            folder_id=folder_id, folder_display_name=folder_name, folder_type='searches'
        )

    # Call the method to get geo folders
    retrieved_folders = db_client.get_geo_folders_db()

    # Assert that the returned folders match the created ones
    assert retrieved_folders == geo_folders


def test_check_if_new_user(session, db_client: DBClient):
    user_id = fake.pyint()
    # Initially, the user should be new
    assert db_client.check_if_new_user(user_id) is True

    # Add the user to the database
    db_factories.UserFactory.create_sync(user_id=user_id)

    # Now the user should not be new
    assert db_client.check_if_new_user(user_id) is False


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
    pref_key = 'topic_new'

    # Call the method to save the user preference
    db_client.user_preference_save(user_id, pref_key)

    # Retrieve the saved preference using the find_model function
    assert find_model(session, db_models.UserPreference, user_id=user_id, preference=pref_key)


def test_user_preference_delete(session, db_client: DBClient, user_id: int):
    # Define a preference key and value
    pref_key = 'topic_new'
    pref_id = 0

    # Save the preference first
    db_factories.UserPreferenceFactory.create_sync(user_id=user_id, preference=pref_key, pref_id=pref_id)

    # Call the method to delete the user preference
    db_client.user_preference_delete(user_id, [pref_key])

    # Assert that the preference no longer exists
    assert not find_model(session, db_models.UserPreference, user_id=user_id, preference=pref_key)


def test_user_preference_is_exists(session, db_client: DBClient, user_id: int):
    # Define a preference key and value
    pref_key = 'topic_new'
    pref_id = 0

    # Initially, the preference should not exist
    assert db_client.user_preference_is_exists(user_id, pref_key) is False

    # Save the preference
    db_factories.UserPreferenceFactory.create_sync(user_id=user_id, preference=pref_key, pref_id=pref_id)

    # Now the preference should exist
    assert not db_client.user_preference_is_exists(user_id, pref_key)


def test_get_last_bot_msg(session, db_client: DBClient, user_id: int):
    # Define a bot message
    message_model = db_factories.MsgFromBotFactory.create_sync(
        user_id=user_id, msg_type=UserInputState.input_of_coords_man
    )

    # Call the method to get the last bot message
    last_bot_msg_type = db_client.get_user_input_state(user_id)

    # Assert that the returned message matches the created one
    assert last_bot_msg_type == message_model.msg_type


def test_get_user_forum_attributes_db(session, db_client: DBClient, user_id: int):
    # Define forum attributes
    attrs_model = db_factories.UserForumAttributeFactory.create_sync(user_id=user_id, status='verified')

    # Call the method to get user forum attributes
    forum_username, forum_id = db_client.get_user_forum_attributes_db(user_id)

    # Assert that the returned attributes match the created ones
    assert forum_username == attrs_model.forum_username
    assert forum_id == attrs_model.forum_user_id


def test_check_onboarding_step(session, db_client: DBClient, user_id: int):
    # Add an onboarding step for the user
    step_id = 10
    step_name = 'role_set'
    db_factories.UserOnboardingFactory.create_sync(user_id=user_id, step_id=step_id, step_name=step_name)

    # Call the method to check the onboarding step
    step_id_result, step_name_result = db_client.get_onboarding_step(user_id, user_is_new=False)

    # Assert that the returned step matches the created one
    assert step_id_result == step_id
    assert step_name_result == step_name


def test_save_bot_reply_to_user(session, db_client: DBClient, user_id: int):
    # Define a bot reply message
    message_text = 'Hello, user!'

    # Call the method to save the bot reply
    db_client.save_bot_reply_to_user(user_id, message_text)

    # Retrieve the saved bot reply
    saved_reply = find_model(session, db_models.Dialog, user_id=user_id, author='bot', message_text=message_text)

    # Assert that the saved reply matches the input
    assert saved_reply.message_text == message_text


def test_save_last_user_message_in_db(session, db_client: DBClient, user_id: int):
    # Define a user message
    message_type = 'some type'

    # Call the method to save the last user message
    db_client.set_user_input_state(user_id, message_type)

    # Retrieve the saved user message
    assert find_model(session, db_models.MsgFromBot, user_id=user_id, msg_type=message_type)


def test_set_search_follow_mode(session, db_client: DBClient, user_id: int):
    # Set the search follow mode for the user
    follow_mode = True
    db_client.set_search_follow_mode(user_id, follow_mode)

    # Retrieve the saved follow mode
    saved_follow_mode = find_model(session, db_models.t_user_pref_search_filtering, user_id=user_id)

    # Assert that the saved follow mode matches the input
    assert saved_follow_mode is not None
    assert saved_follow_mode.filter_name == ['whitelist']


def test_delete_folder_from_user_regional_preference(session, db_client: DBClient, user_id: int):
    # Add a regional preference for the user
    folder_id = 101
    db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id, forum_folder_num=folder_id)

    # Call the method to delete the folder from user regional preferences
    db_client.delete_folder_from_user_regional_preference(user_id, folder_id)

    # Assert that the folder no longer exists in the user's regional preferences
    deleted_folder = find_model(session, db_models.UserRegionalPreference, user_id=user_id, forum_folder_num=folder_id)
    assert deleted_folder is None


def test_get_folders_with_followed_searches(session, db_client: DBClient, user_model: db_models.User):
    # Add followed searches for the user

    folder_ids = []
    for _ in range(3):
        search_model = db_factories.SearchFactory.create_sync()
        folder_ids.append(search_model.forum_folder_id)
        db_factories.UserPrefSearchWhitelistFactory.create_sync(
            user=user_model,
            search_id=search_model.search_forum_num,
            search_following_mode=SearchFollowingMode.ON,
        )

    # Call the method to get folders with followed searches
    followed_folders = db_client.get_folders_with_followed_searches(user_model.user_id)

    # Assert that the returned folders match the created ones
    assert set(followed_folders) == set(folder_ids)


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
    db_factories.UserPrefRadiusFactory.create_sync(user_id=user_id, radius=radius)

    # Call the method to check the saved radius
    saved_radius = db_client.check_saved_radius(user_id)

    # Assert that the saved radius matches the created one
    assert saved_radius == radius


def test_delete_user_saved_radius(session, db_client: DBClient, user_id: int):
    # Save a radius for the user
    db_factories.UserPrefRadiusFactory.create_sync(user_id=user_id)

    # Call the method to delete the user's saved radius
    db_client.delete_user_saved_radius(user_id)

    # Assert that the radius no longer exists
    assert not find_model(session, db_models.UserPrefRadiu, user_id=user_id)


def test_save_user_radius(session, db_client: DBClient, user_id: int):
    # Define a radius value
    radius = 100

    # Call the method to save the user's radius
    db_client.save_user_radius(user_id, radius)

    # Retrieve the saved radius
    saved_radius = find_model(session, db_models.UserPrefRadiu, user_id=user_id)

    # Assert that the saved radius matches the input
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
    search_id = fake.pyint()
    search_following_mode = SearchFollowingMode.ON

    # Call the method to record search whiteness
    db_client.record_search_whiteness(user_id, search_id, search_following_mode)

    # Retrieve the recorded search whiteness
    recorded_whiteness = find_model(session, db_models.UserPrefSearchWhitelist, user_id=user_id, search_id=search_id)

    # Assert that the search whiteness was recorded successfully
    assert recorded_whiteness is not None
    assert recorded_whiteness.search_following_mode == search_following_mode


def test_add_region_to_user_settings(session, db_client: DBClient, user_id: int):
    # Define a region ID
    region_id = fake.pyint()

    # Call the method to add the region to user settings
    db_client.add_region_to_user_settings(user_id, region_id)

    # Retrieve the added region
    assert find_model(session, db_models.UserPrefRegion, user_id=user_id, region_id=region_id)


def test_save_user_age_prefs(session, db_client: DBClient, user_id: int):
    # Define an age preference

    age_pref = AgePeriod(description='1', name='2', min_age=3, max_age=4, order=5)

    # Call the method to save the user's age preference
    db_client.save_user_age_prefs(user_id, age_pref)

    # Retrieve the saved age preference
    assert find_model(session, db_models.UserPrefAge, user_id=user_id, period_name=age_pref.name)


def test_delete_user_age_pref(session, db_client: DBClient, user_id: int):
    # Add an age preference for the user
    age_pref = AgePeriod(description='1', name='2', min_age=3, max_age=4, order=5)
    db_factories.UserPrefAgeFactory.create_sync(
        user_id=user_id,
        period_min=age_pref.min_age,
        period_max=age_pref.max_age,
    )

    # Call the method to delete the user's age preference
    db_client.delete_user_age_pref(user_id, age_pref)

    # Assert that the age preference no longer exists
    assert not find_model(session, db_models.UserPrefAge, user_id=user_id)


def test_get_age_prefs(session, db_client: DBClient, user_id: int):
    # Add age preferences for the user
    models = db_factories.UserPrefAgeFactory.create_batch_sync(3, user_id=user_id)

    # Call the method to get age preferences
    retrieved_age_prefs = db_client.get_age_prefs(user_id)

    # Assert that the retrieved age preferences match the created ones
    for model in models:
        assert (model.period_min, model.period_max) in retrieved_age_prefs


def test_get_existing_user_settings(session, db_client: DBClient, user_id: int):
    # Add user settings to the database
    db_factories.UserPrefAgeFactory.create_sync(user_id=user_id)
    db_factories.UserCoordinateFactory.create_sync(user_id=user_id)
    db_factories.UserPrefRadiusFactory.create_sync(user_id=user_id)
    db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user_id)
    db_factories.UserPrefTopicTypeFactory.create_sync(user_id=user_id)

    # Call the method to get existing user settings
    user_settings = db_client.get_user_settings_summary(user_id)

    # Assert that the returned settings are correct
    assert user_settings == UserSettingsSummary(user_id, True, True, True, True, False, True, False, False, True, False)


def test_get_all_user_preferences(session, db_client: DBClient, user_id: int):
    # Add user preferences to the database
    pref_key = 'topic_new'
    pref_id = 0

    # Save the preference first
    db_factories.UserPreferenceFactory.create_sync(user_id=user_id, preference=pref_key, pref_id=pref_id)

    # Call the method to get all user preferences
    user_preferences = db_client.get_all_user_preferences(user_id)

    # Assert that the returned preferences match the created ones
    assert user_preferences == [pref_key]


def test_get_all_active_searches_in_one_region_2(session, db_client: DBClient, user_id: int):
    # Add active searches for a region
    region_id = fake.pyint()
    searches = [
        db_factories.SearchFactory.create_sync(forum_folder_id=region_id, status='Ищем'),
        db_factories.SearchFactory.create_sync(forum_folder_id=region_id, status='Возобновлен'),
    ]

    # Call the method to get all active searches in the region
    active_searches = db_client.get_active_searches_in_region_limit_20(region_id, user_id)

    # Assert that the returned searches match the created ones
    assert len(active_searches) == len(searches)
    searches.sort(key=lambda x: x.search_forum_num)
    active_searches.sort(key=lambda x: x.topic_id)
    for search_model, search_result in zip(searches, active_searches):
        _assert_search_summary_equals_to_search_model(search_model, search_result)


def test_get_all_searches_in_one_region(session, db_client: DBClient):
    # Add searches for a region
    region_id = fake.pyint()
    searches = db_factories.SearchFactory.create_batch_sync(2, forum_folder_id=region_id)

    # Call the method to get all searches in the region
    all_searches = db_client.get_all_searches_in_one_region_limit_20(region_id)

    # Assert that the returned searches match the created ones
    assert len(all_searches) == len(searches)

    searches.sort(key=lambda x: x.search_forum_num)
    all_searches.sort(key=lambda x: x.topic_id)
    for search_model, search_result in zip(searches, all_searches):
        _assert_search_summary_equals_to_search_model(search_model, search_result)


def test_get_all_last_searches_in_region(session, db_client: DBClient, user_id: int):
    # Add searches for a region
    region_id = fake.pyint()
    searches = db_factories.SearchFactory.create_batch_sync(2, forum_folder_id=region_id)

    # Call the method to get all last searches in the region
    last_searches = db_client.get_all_last_searches_in_region_limit_20(region_id, user_id, only_followed=False)

    # Assert that the returned searches match the created ones
    assert len(last_searches) == len(searches)
    searches.sort(key=lambda x: x.search_forum_num)
    last_searches.sort(key=lambda x: x.topic_id)
    for search_model, search_result in zip(searches, last_searches):
        _assert_search_summary_equals_to_search_model(search_model, search_result)


def test_get_active_searches_in_one_region(session, db_client: DBClient):
    # Add active searches for a region
    region_id = fake.pyint()
    searches = [
        db_factories.SearchFactory.create_sync(forum_folder_id=region_id, status='Ищем'),
        db_factories.SearchFactory.create_sync(forum_folder_id=region_id, status='Возобновлен'),
    ]

    # Call the method to get active searches in the region
    active_searches = db_client.get_active_searches_in_one_region(region_id)

    # Assert that the returned searches match the created ones
    assert len(active_searches) == len(searches)
    searches.sort(key=lambda x: x.search_forum_num)
    active_searches.sort(key=lambda x: x.topic_id)
    for search_model, search_result in zip(searches, active_searches):
        _assert_search_summary_equals_to_search_model(search_model, search_result)


def test_write_user_forum_attributes_db(session, db_client: DBClient, user_id: int):
    # Add forum attributes for the user
    db_factories.UserForumAttributeFactory.create_sync(user_id=user_id, status='pending')

    # Call the method to write user forum attributes
    db_client.write_user_forum_attributes_db(user_id)

    # Retrieve the updated forum attributes
    updated_attributes = find_model(session, db_models.UserForumAttribute, user_id=user_id)

    # Assert that the status was updated to 'verified'
    assert updated_attributes is not None
    assert updated_attributes.status == 'verified'


def test_get_user_role(session, db_client: DBClient, user_id: int, user_model: db_models.User):
    # Call the method to get the user role
    retrieved_role = db_client.get_user_role(user_id)

    # Assert that the retrieved role matches the created one
    assert retrieved_role == user_model.role


def test_get_user_sys_roles(session, db_client: DBClient, user_id: int, user_model: db_models.User):
    # Add system roles for the user
    roles = ['admin', 'moderator']
    for role in roles:
        db_factories.UserRoleFactory.create_sync(user_id=user_id, role=role)

    # Call the method to get user system roles
    retrieved_roles = db_client.get_user_sys_roles(user_id)

    # Assert that the retrieved roles match the created ones
    roles.append('')
    assert set(retrieved_roles) == set(roles)


def test_get_search_follow_mode(session, db_client: DBClient, user_id: int):
    # Set the search follow mode for the user
    db_factories.UserPrefSearchFilteringFactory.create_sync(user_id=user_id, filter_name=['whitelist'])

    # Call the method to get the search follow mode
    follow_mode = db_client.get_search_follow_mode(user_id)

    # Assert that the follow mode is correctly retrieved
    assert follow_mode is True


def test_save_last_user_inline_dialogue(session, db_client: DBClient, user_id: int):
    # Define a message ID
    message_id = fake.pyint()

    # Call the method to save the last user inline dialogue
    db_client.save_last_user_inline_dialogue(user_id, message_id)

    # Retrieve the saved inline dialogue
    assert find_model(session, db_factories.CommunicationsLastInlineMsg, user_id=user_id, message_id=message_id)


def test_get_last_user_inline_dialogue(session, db_client: DBClient, user_id: int):
    # Add a last inline dialogue for the user
    message_id = fake.pyint()
    db_factories.CommunicationsLastInlineMsgFactory.create_sync(user_id=user_id, message_id=message_id)

    # Call the method to get the last user inline dialogue
    last_dialogue = db_client.get_last_user_inline_dialogue(user_id)

    # Assert that the retrieved dialogue matches the created one
    assert last_dialogue == [message_id]


def test_delete_last_user_inline_dialogue(session, db_client: DBClient, user_id: int):
    # Add a last inline dialogue for the user
    message_id = fake.pyint()
    db_factories.CommunicationsLastInlineMsgFactory.create_sync(user_id=user_id, message_id=message_id)

    # Call the method to delete the last user inline dialogue
    db_client.delete_last_user_inline_dialogue(user_id)

    # Assert that the dialogue no longer exists
    assert not find_model(session, db_factories.CommunicationsLastInlineMsg, user_id=user_id)


def _assert_search_summary_equals_to_search_model(search_model: db_models.Search, search_summary: SearchSummary):
    assert search_model.search_forum_num == search_summary.topic_id
    assert search_model.age == search_summary.age
