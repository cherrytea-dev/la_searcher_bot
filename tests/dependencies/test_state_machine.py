"""Tests for the shared state machine module."""

from random import randint

import pytest
from sqlalchemy.engine import Connection

from _dependencies.state_machine import DialogState, clear_user_state, get_user_state, set_user_state
from tests.common import find_model
from tests.factories import db_factories, db_models


@pytest.fixture
def user_id() -> int:
    return randint(1, 1_000_000)


class TestSetUserState:
    def test_set_state_radius_input(self, user_id: int):
        """Test setting radius_input state."""
        set_user_state(user_id, DialogState.radius_input)

        saved = find_model(db_factories.get_session(), db_models.MsgFromBot, user_id=user_id)
        assert saved is not None
        assert saved.msg_type == DialogState.radius_input

    def test_set_state_input_of_coords_man(self, user_id: int):
        """Test setting input_of_coords_man state."""
        set_user_state(user_id, DialogState.input_of_coords_man)

        saved = find_model(db_factories.get_session(), db_models.MsgFromBot, user_id=user_id)
        assert saved is not None
        assert saved.msg_type == DialogState.input_of_coords_man

    def test_set_state_input_of_forum_username(self, user_id: int):
        """Test setting input_of_forum_username state."""
        set_user_state(user_id, DialogState.input_of_forum_username)

        saved = find_model(db_factories.get_session(), db_models.MsgFromBot, user_id=user_id)
        assert saved is not None
        assert saved.msg_type == DialogState.input_of_forum_username

    def test_set_state_not_defined(self, user_id: int):
        """Test setting not_defined state."""
        set_user_state(user_id, DialogState.not_defined)

        saved = find_model(db_factories.get_session(), db_models.MsgFromBot, user_id=user_id)
        assert saved is not None
        assert saved.msg_type == DialogState.not_defined

    def test_set_state_overwrites_previous(self, user_id: int):
        """Test that setting a new state overwrites the previous one."""
        # Set initial state
        set_user_state(user_id, DialogState.radius_input)

        # Overwrite with new state
        set_user_state(user_id, DialogState.input_of_coords_man)

        session = db_factories.get_session()
        saved = list(session.query(db_models.MsgFromBot).filter_by(user_id=user_id).all())
        # Should only have one record (overwritten)
        assert len(saved) == 1
        assert saved[0].msg_type == DialogState.input_of_coords_man


class TestGetUserState:
    def test_get_state_when_no_state(self, user_id: int):
        """Test getting state when no state is set."""
        state = get_user_state(user_id)
        assert state is None

    def test_get_state_radius_input(self, user_id: int):
        """Test getting radius_input state."""
        db_factories.MsgFromBotFactory.create_sync(user_id=user_id, msg_type=DialogState.radius_input)

        state = get_user_state(user_id)
        assert state == DialogState.radius_input

    def test_get_state_input_of_coords_man(self, user_id: int):
        """Test getting input_of_coords_man state."""
        db_factories.MsgFromBotFactory.create_sync(user_id=user_id, msg_type=DialogState.input_of_coords_man)

        state = get_user_state(user_id)
        assert state == DialogState.input_of_coords_man

    def test_get_state_input_of_forum_username(self, user_id: int):
        """Test getting input_of_forum_username state."""
        db_factories.MsgFromBotFactory.create_sync(user_id=user_id, msg_type=DialogState.input_of_forum_username)

        state = get_user_state(user_id)
        assert state == DialogState.input_of_forum_username

    def test_get_state_not_defined(self, user_id: int):
        """Test getting not_defined state."""
        db_factories.MsgFromBotFactory.create_sync(user_id=user_id, msg_type=DialogState.not_defined)

        state = get_user_state(user_id)
        assert state == DialogState.not_defined

    def test_get_state_returns_first_if_multiple(self, user_id: int):
        """Test that get_state returns the first record if multiple exist."""
        db_factories.MsgFromBotFactory.create_sync(user_id=user_id, msg_type=DialogState.radius_input)
        db_factories.MsgFromBotFactory.create_sync(user_id=user_id, msg_type=DialogState.input_of_coords_man)

        state = get_user_state(user_id)
        # Should return the first one (radius_input)
        assert state == DialogState.radius_input

    def test_get_state_unknown_type_returns_none(self, user_id: int):
        """Test that an unknown msg_type returns None."""
        db_factories.MsgFromBotFactory.create_sync(user_id=user_id, msg_type='some_unknown_type')

        state = get_user_state(user_id)
        assert state is None


class TestClearUserState:
    def test_clear_state_sets_not_defined(self, user_id: int):
        """Test that clear_user_state sets state to not_defined."""
        # Set a state first
        set_user_state(user_id, DialogState.radius_input)

        # Clear it
        clear_user_state(user_id)

        saved = find_model(db_factories.get_session(), db_models.MsgFromBot, user_id=user_id)
        assert saved is not None
        assert saved.msg_type == DialogState.not_defined

    def test_clear_state_when_no_state(self, user_id: int):
        """Test clearing state when no state exists creates not_defined."""
        clear_user_state(user_id)

        saved = find_model(db_factories.get_session(), db_models.MsgFromBot, user_id=user_id)
        assert saved is not None
        assert saved.msg_type == DialogState.not_defined

    def test_clear_state_overwrites_previous(self, user_id: int):
        """Test that clear_state overwrites any previous state."""
        db_factories.MsgFromBotFactory.create_sync(user_id=user_id, msg_type=DialogState.input_of_forum_username)

        clear_user_state(user_id)

        session = db_factories.get_session()
        saved = list(session.query(db_models.MsgFromBot).filter_by(user_id=user_id).all())
        assert len(saved) == 1
        assert saved[0].msg_type == DialogState.not_defined
