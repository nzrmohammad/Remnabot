from aiogram.fsm.state import State, StatesGroup


class ServiceRequestStates(StatesGroup):
    """«درخواست سرویس جدید» / free trial and coupon input."""
    waiting_text = State()
    waiting_trial_username = State()
    waiting_coupon = State()
