"""Admin Store Core Settings, Reminders, Grace Period, and FSM Wizard.

Decomposed into:
- admin_settings_common.py: Constants, descriptions, helper functions.
- admin_settings_views.py: Dashboard overview render, boolean toggles, maintenance mode.
- admin_settings_pickers.py: Expiry reminder multi-select, grace period picker, squad selection.
- admin_settings_wizard.py: FSM wizard handlers for input validation and saving.
"""
from aiogram import F, Router

from bot.common import is_admin
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.user_repo import UserRepository
from bot.handlers.admin_settings_common import (
    SETTING_DESCRIPTIONS,
    SETTING_FIELDS,
    _is_admin,
    _parse_int,
    delete_message_silently,
    render_menu,
)
from bot.handlers.admin_settings_pickers import (
    GRACE_DAYS_CHOICES,
    REMIND_DAYS_CHOICES,
    _parse_remind_days_set,
    _render_grace_days_picker,
    _render_remind_days_picker,
    grace_days_picker_entry,
    grace_days_set,
    remind_days_picker_entry,
    remind_days_toggle,
    settings_set_squad,
)
from bot.handlers.admin_settings_views import (
    _render_settings,
    maintenance_toggle,
    setting_toggle_boolean,
    store_settings_view,
)
from bot.handlers.admin_settings_wizard import (
    settings_edit_start,
    settings_value_save,
)
from bot.services.app_settings import (
    get_store_settings,
    is_maintenance,
    set_maintenance,
)
from bot.states.admin import SettingsStates

router = Router(name="admin_settings_store")

# Register routes to preserve identical router structure
router.callback_query.register(store_settings_view, F.data == "adm:settings")
router.callback_query.register(setting_toggle_boolean, F.data.startswith("adm:settings:toggle:"))
router.callback_query.register(maintenance_toggle, F.data == "adm:maint")
router.callback_query.register(remind_days_picker_entry, F.data == "adm:remind:picker")
router.callback_query.register(remind_days_toggle, F.data.startswith("adm:remind:toggle:"))
router.callback_query.register(grace_days_picker_entry, F.data == "adm:grace:picker")
router.callback_query.register(grace_days_set, F.data.startswith("adm:grace:set:"))
router.callback_query.register(settings_edit_start, F.data.startswith("adm:set:"))
router.callback_query.register(settings_set_squad, F.data.startswith("adm:setsquad:"))
router.message.register(settings_value_save, SettingsStates.waiting_value, F.text)

__all__ = [
    "router",
    "render_menu",
    "delete_message_silently",
    "_is_admin",
    "is_admin",
    "_parse_int",
    "SETTING_FIELDS",
    "SETTING_DESCRIPTIONS",
    "REMIND_DAYS_CHOICES",
    "_parse_remind_days_set",
    "_render_remind_days_picker",
    "remind_days_picker_entry",
    "remind_days_toggle",
    "GRACE_DAYS_CHOICES",
    "_render_grace_days_picker",
    "grace_days_picker_entry",
    "grace_days_set",
    "settings_set_squad",
    "_render_settings",
    "store_settings_view",
    "setting_toggle_boolean",
    "maintenance_toggle",
    "settings_edit_start",
    "settings_value_save",
    "get_store_settings",
    "is_maintenance",
    "set_maintenance",
    "AppSettingRepository",
    "AdminLogRepository",
    "UserRepository",
]
