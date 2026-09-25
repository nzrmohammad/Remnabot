"""FSM states for the wallet top-up flow."""
from aiogram.fsm.state import State, StatesGroup


class TopupStates(StatesGroup):
    waiting_amount = State()
    waiting_receipt = State()
