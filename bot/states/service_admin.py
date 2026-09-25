from aiogram.fsm.state import State, StatesGroup


class ServiceAdminStates(StatesGroup):
    """Guided 'create a service' form plus a single 'edit a field' step."""

    create_name = State()
    create_price = State()
    create_duration = State()
    create_traffic = State()
    create_strategy = State()   # chosen via inline buttons
    create_hwid = State()
    create_squad = State()
    create_description = State()

    edit_value = State()  # state.data holds: service_id + field
