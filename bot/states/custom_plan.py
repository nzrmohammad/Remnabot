"""FSM states for the Custom Plan builder flow."""
from aiogram.fsm.state import State, StatesGroup


class CustomPlanStates(StatesGroup):
    waiting_for_custom_gb = State()
    waiting_for_custom_days = State()
