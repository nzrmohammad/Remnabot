"""Admin Users Management API endpoints (Facade module).

Decomposed into focused domain submodules:
- `bot.web.admin_users_list`: User listing, search, pagination, and bulk actions
- `bot.web.admin_users_detail`: Sessions, HWID devices, and SRH request history
- `bot.web.admin_users_actions`: Modifying user plans, wallet, bans, and revoking sub
"""

from bot.web.admin_users_actions import (
    post_admin_kill_sessions,
    post_admin_modify_user,
    post_admin_reset_trial,
    post_admin_toggle_ban,
    post_admin_user_revoke_sub,
    post_admin_user_wallet,
)
from bot.web.admin_users_detail import (
    get_admin_sessions_explorer,
    get_admin_user_hwid_devices,
    get_admin_user_sessions,
    get_admin_user_srh,
    post_admin_user_delete_hwid,
)
from bot.web.admin_users_list import (
    get_admin_users,
    post_admin_users_bulk_action,
)

__all__ = [
    "get_admin_sessions_explorer",
    "get_admin_user_hwid_devices",
    "get_admin_user_sessions",
    "get_admin_user_srh",
    "get_admin_users",
    "post_admin_kill_sessions",
    "post_admin_modify_user",
    "post_admin_reset_trial",
    "post_admin_toggle_ban",
    "post_admin_user_delete_hwid",
    "post_admin_user_revoke_sub",
    "post_admin_user_wallet",
    "post_admin_users_bulk_action",
]
