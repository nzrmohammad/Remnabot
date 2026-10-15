"""Admin API endpoints for Telegram Mini App Management Suite.

Central router aggregating domain-specific modular handlers:
- `bot.web.admin_overview`: Dashboard KPIs, cluster metrics, and strategic charts.
- `bot.web.admin_users`: User accounts, sessions, SRH, HWID, and batch operations.
- `bot.web.admin_tickets`: Support tickets and bidirectional chat.
- `bot.web.admin_plans`: Services, packages, and coupon management.
- `bot.web.admin_topups`: Wallet topup verification and receipt inspection.
- `bot.web.admin_campaigns`: Mass messaging, broadcasts, and marketing campaigns.
- `bot.web.admin_settings_api`: Runtime app settings and crypto rates.
- `bot.web.admin_infra_api`: Infrastructure billing and node cost management.
"""

# Re-export modular domain handlers for seamless backward-compatibility
from bot.web.admin_common import _check_admin
from bot.web.admin_overview import get_admin_overview
from bot.web.admin_users import (
    get_admin_users,
    post_admin_modify_user,
    post_admin_kill_sessions,
    post_admin_toggle_ban,
    post_admin_reset_trial,
    post_admin_user_wallet,
    post_admin_user_revoke_sub,
    get_admin_user_hwid_devices,
    get_admin_user_sessions,
    get_admin_sessions_explorer,
    get_admin_user_srh,
    post_admin_users_bulk_action,
    post_admin_user_delete_hwid,
)
from bot.web.admin_tickets import (
    get_admin_ticket_threads,
    get_admin_ticket_messages,
    post_admin_reply_ticket,
)
from bot.web.admin_plans import (
    get_admin_plans,
    post_admin_plan_save,
    post_admin_plan_toggle,
    post_admin_plan_delete,
    get_admin_coupons,
    post_admin_coupon_save,
    post_admin_coupon_toggle,
    post_admin_coupon_delete,
    get_admin_coupon_usages,
    post_admin_batch_vouchers,
)
from bot.web.admin_topups import (
    get_admin_topups,
    post_admin_topup_action,
    get_admin_topup_photo,
)
from bot.web.admin_campaigns import (
    _BROADCAST_STATUSES,
    post_admin_broadcast,
    get_admin_broadcast_status,
    get_admin_campaigns,
    post_admin_campaign_create,
    post_admin_campaign_delete,
)
from bot.web.admin_settings_api import (
    get_admin_settings,
    post_admin_settings,
    get_admin_crypto_rates,
)
from bot.web.admin_infra_api import (
    get_admin_infra_billing,
    post_admin_node_cost,
    get_admin_ssl_health,
    post_admin_ssl_check,
    post_admin_add_ssl_domain,
    post_admin_delete_ssl_domain,
)

__all__ = [
    "get_admin_overview",
    "get_admin_users",
    "post_admin_modify_user",
    "post_admin_kill_sessions",
    "post_admin_toggle_ban",
    "post_admin_reset_trial",
    "post_admin_user_wallet",
    "post_admin_user_revoke_sub",
    "get_admin_user_hwid_devices",
    "get_admin_user_sessions",
    "get_admin_sessions_explorer",
    "get_admin_user_srh",
    "post_admin_users_bulk_action",
    "post_admin_user_delete_hwid",
    "get_admin_ticket_threads",
    "get_admin_ticket_messages",
    "post_admin_reply_ticket",
    "get_admin_plans",
    "post_admin_plan_save",
    "post_admin_plan_toggle",
    "post_admin_plan_delete",
    "get_admin_coupons",
    "post_admin_coupon_save",
    "post_admin_coupon_toggle",
    "post_admin_coupon_delete",
    "get_admin_coupon_usages",
    "post_admin_batch_vouchers",
    "get_admin_topups",
    "post_admin_topup_action",
    "get_admin_topup_photo",
    "_BROADCAST_STATUSES",
    "post_admin_broadcast",
    "get_admin_broadcast_status",
    "get_admin_campaigns",
    "post_admin_campaign_create",
    "post_admin_campaign_delete",
    "get_admin_settings",
    "post_admin_settings",
    "get_admin_crypto_rates",
    "get_admin_infra_billing",
    "post_admin_node_cost",
    "get_admin_ssl_health",
    "post_admin_ssl_check",
    "post_admin_add_ssl_domain",
    "post_admin_delete_ssl_domain",
]
