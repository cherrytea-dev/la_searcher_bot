from unittest.mock import MagicMock

import pytest

from communicate._utils.database import DBClient
from communicate._utils.handler_context import TGHandlerContext
from communicate._utils.handlers import button_handlers, notification_settings_handlers
from tests.factories import db_factories, db_models


@pytest.fixture
def tg_handler_context(db_client: DBClient) -> TGHandlerContext:
    """Create a minimal TGHandlerContext for testing helper functions."""
    update_params = MagicMock()
    update_params.user_id = 0
    return TGHandlerContext(
        update_params=update_params,
        extra_params=MagicMock(),
        db=db_client,
        tg_api=MagicMock(),
    )


def test_compose_msg_on_user_setting_fullness(
    session, db_client: DBClient, user_id: int, user_model: db_models.User, tg_handler_context: TGHandlerContext
):
    db_factories.UserPrefAgeFactory.create_sync(user_id=user_id)

    message = button_handlers._compose_msg_on_user_setting_fullness(tg_handler_context, user_id)

    assert message is not None
    assert 'Вы настроили бот' in message
    assert 'Возрастные группы БВП' not in message


def test_compose_user_preferences_message(
    session, db_client: DBClient, user_id: int, user_model: db_models.User, tg_handler_context: TGHandlerContext
):
    db_factories.UserPreferenceFactory.create_sync(user_id=user_id, preference='status_changes')

    summary, pref_list = notification_settings_handlers._compose_user_preferences_message(tg_handler_context, user_id)

    assert pref_list == ['status_changes']
    assert 'об изменении статуса' in summary
