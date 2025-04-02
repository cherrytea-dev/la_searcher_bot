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

