"""Admin Store Settings, Topics, Crypto, Trial/Referral, and Maintenance Modes."""
import logging

from aiogram import Router

from bot.common import is_admin, parse_int
from bot.handlers.admin_settings_crypto import (
    _render_crypto_settings,
    apply_nobitex_rate,
    crypto_nobitex_now,
    crypto_settings_view,
    router as crypto_router,
    toggle_crypto_enabled,
)
from bot.handlers.admin_settings_store import (
    GRACE_DAYS_CHOICES,
    REMIND_DAYS_CHOICES,
    SETTING_DESCRIPTIONS,
    SETTING_FIELDS,
    _parse_remind_days_set,
    _render_grace_days_picker,
    _render_remind_days_picker,
    _render_settings,
    grace_days_picker_entry,
    grace_days_set,
    maintenance_toggle,
    remind_days_picker_entry,
    remind_days_toggle,
    router as store_router,
    setting_toggle_boolean,
    settings_edit_start,
    settings_set_squad,
    settings_value_save,
    store_settings_view,
)
from bot.handlers.admin_settings_topics import (
    _cached_admin_group_title,
    _cached_admin_group_title_time,
    _render_topics_settings,
    get_admin_group_title,
    router as topics_router,
    topics_settings_view,
)
from bot.handlers.admin_settings_trial_referral import (
    _render_referral_settings,
    _render_trial_settings,
    referral_settings_view,
    router as trial_ref_router,
    trial_ref_settings_view,
    trial_settings_view,
)

logger = logging.getLogger(__name__)

router = Router(name="admin_settings")
router.include_router(crypto_router)
router.include_router(topics_router)
router.include_router(trial_ref_router)
router.include_router(store_router)

_parse_int = parse_int
_get_admin_group_title = get_admin_group_title


_is_admin = is_admin


__all__ = [
    "router",
    "_parse_int",
    "_is_admin",
    "SETTING_FIELDS",
    "SETTING_DESCRIPTIONS",
    "_cached_admin_group_title",
    "_cached_admin_group_title_time",
    "_get_admin_group_title",
    "get_admin_group_title",
    "_render_settings",
    "store_settings_view",
    "_render_topics_settings",
    "topics_settings_view",
    "_render_crypto_settings",
    "crypto_settings_view",
    "toggle_crypto_enabled",
    "crypto_nobitex_now",
    "apply_nobitex_rate",
    "_render_trial_settings",
    "_render_referral_settings",
    "trial_settings_view",
    "referral_settings_view",
    "trial_ref_settings_view",
    "setting_toggle_boolean",
    "maintenance_toggle",
    "REMIND_DAYS_CHOICES",
    "_parse_remind_days_set",
    "_render_remind_days_picker",
    "remind_days_picker_entry",
    "remind_days_toggle",
    "GRACE_DAYS_CHOICES",
    "_render_grace_days_picker",
    "grace_days_picker_entry",
    "grace_days_set",
    "settings_edit_start",
    "settings_set_squad",
    "settings_value_save",
]
