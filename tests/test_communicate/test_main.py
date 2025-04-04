from unittest.mock import MagicMock, Mock

import pytest
from psycopg2.extensions import cursor

import communicate._utils.common
import communicate._utils.handlers
import communicate._utils.message_sending
from _dependencies.commons import get_app_config
from communicate._utils import buttons
from communicate._utils.database import DBClient, db
from tests.factories.telegram import get_callback_query, get_reply_markup


@pytest.fixture(scope='session', autouse=True)
def db_client() -> DBClient:
    db_cln = db()
    with db_cln.connect():
        yield db_cln


def test_manage_search_follow_mode():
    user_action = 'search_follow_mode_on'
    bot_answer = communicate._utils.handlers.manage_search_follow_mode('1', {'action': user_action}, 2, 3, 'token')
    assert bot_answer == 'Режим выбора поисков для отслеживания включен.'

    user_action = 'search_follow_mode_off'
    bot_answer = communicate._utils.handlers.manage_search_follow_mode('1', {'action': user_action}, 2, 3, 'token')
    assert bot_answer == 'Режим выбора поисков для отслеживания отключен.'


def test_manage_search_whiteness(db_client):
    cb_query = get_callback_query()
    user_callback = {'action': 'search_follow_mode', 'hash': '123', 'text': '   '}
    res = communicate._utils.handlers.manage_search_whiteness(1, user_callback, 1, cb_query, 'token')

    assert res[0] == 'foo'


def test_manage_topic_type(db_client):
    cb_query = get_callback_query()
    user_callback = {'action': 'on', 'hash': '7bf077a5', 'text': '   '}
    res = communicate._utils.handlers.manage_topic_type(
        1,
        'foo',
        communicate._utils.common.AllButtons(buttons.full_buttons_dict),
        user_callback,
        1,
        'token',
        cb_query,
    )

    assert (
        res[0]
        == 'Вы можете выбрать и в любой момент поменять, по каким типам поисков или мероприятий бот должен присылать уведомления.'
    )


def test_api_callback_edit_inline_keyboard(db_client):
    cb_query = get_callback_query().to_dict()
    res = communicate._utils.message_sending.api_callback_edit_inline_keyboard(
        get_app_config().bot_api_token__prod, cb_query, get_reply_markup(), 1
    )

    assert res == 'failed'


def test_manage_age(db_client):
    res = communicate._utils.handlers.manage_age(1, 'включить: Маленькие Дети 0-6 лет')

    assert res[0][0] == ['отключить: Маленькие Дети 0-6 лет']


def test_save_onboarding_step():
    res = communicate._utils.common.save_onboarding_step(1, 'testuser', 'step')

    assert res is None


def test_send_message_to_api():
    message = 'foo'
    params = {'parse_mode': 'markdown'}
    res = communicate._utils.message_sending.send_message_to_api('token', 1, message, params)

    assert res == 'failed'


def test_send_callback_answer_to_api():
    message = 'foo'
    res = communicate._utils.message_sending.send_callback_answer_to_api('token', 1, message)

    assert res == 'failed'
