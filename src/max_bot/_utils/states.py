"""FSM states for the MAX bot.

Uses ``maxapi``'s ``StatesGroup`` and ``State`` for finite state machine
management during multi-step dialogs (radius input, coordinate input).
"""

from maxapi.context.state_machine import State, StatesGroup


class MaxStates(StatesGroup):
    """FSM states for the MAX bot dialogs."""

    waiting_for_radius = State()
    waiting_for_coords = State()
