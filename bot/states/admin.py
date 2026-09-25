"""FSM states for the admin panel (users, broadcast, store settings)."""
from aiogram.fsm.state import State, StatesGroup


class UserManagementStates(StatesGroup):
    waiting_telegram_id = State()          # «افزودن کاربر» by Telegram ID
    waiting_balance_amount = State()       # amount for add/subtract
    waiting_search = State()               # admin user search query
    create_username = State()              # create panel user: username
    create_traffic = State()               # create panel user: traffic in GB
    create_duration = State()              # create panel user: duration in days
    create_squad = State()                 # create panel user: internal squad selection
    create_hwid = State()                  # create panel user: HWID device limit
    create_telegram_id = State()           # create panel user: telegram ID (optional)
    waiting_extend_days = State()          # quick extend: add days
    waiting_extend_traffic = State()       # quick extend: add traffic (GB)
    waiting_edit_tid = State()             # edit user: bind/unbind telegram ID
    waiting_edit_desc = State()            # edit user: admin description / note


class BroadcastStates(StatesGroup):
    waiting_text = State()


class SettingsStates(StatesGroup):
    waiting_value = State()


class OrderManagementStates(StatesGroup):
    waiting_search = State()


class CouponManagementStates(StatesGroup):
    waiting_code = State()
    waiting_discount = State()
    waiting_max_uses = State()

