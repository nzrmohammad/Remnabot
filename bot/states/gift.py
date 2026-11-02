"""FSM states for the Gift Cards flow."""
from aiogram.fsm.state import State, StatesGroup


class GiftStates(StatesGroup):
    waiting_for_balance_amount = State()
    waiting_for_receiver = State()
    waiting_for_message = State()
