import datetime
from unittest.mock import Mock, patch

import pytest

# from communicate._utils import compose_messages
from communicate._utils.database import DBClient
from communicate._utils.handlers import button_handlers, notification_settings_handlers
from tests.common import fake, find_model
from tests.factories import db_factories, db_models


@pytest.fixture(autouse=True)
def patch_db(db_client: DBClient):
    with (
        patch.object(notification_settings_handlers, 'db', Mock(return_value=db_client)),
        patch.object(button_handlers, 'db', Mock(return_value=db_client)),
    ):
        yield


def test_compose_msg_on_user_setting_fullness(session, db_client: DBClient, user_id: int, user_model: db_models.User):
    db_factories.UserPrefAgeFactory.create_sync(user_id=user_id)

    message = button_handlers._compose_msg_on_user_setting_fullness(user_id)

    assert 'Вы настроили бот' in message
    assert 'Возрастные группы БВП' not in message


def test_compose_user_preferences_message(session, db_client: DBClient, user_id: int, user_model: db_models.User):
    db_factories.UserPreferenceFactory.create_sync(user_id=user_id, preference='status_changes')

    summary, pref_list = notification_settings_handlers._compose_user_preferences_message(user_id)

    assert pref_list == ['status_changes']
    assert 'об изменении статуса' in summary
