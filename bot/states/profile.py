"""FSM states for profile management (e.g. birthday registration)."""
from aiogram.fsm.state import State, StatesGroup


class ProfileStates(StatesGroup):
    waiting_for_birthday = State()
