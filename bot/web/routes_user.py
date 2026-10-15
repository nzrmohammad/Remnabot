from bot.web.user_common import require_user
"""User API endpoints for Telegram Mini App.

Modularized into domain-specific modules:
- user_profile.py: Dashboard telemetry, user details, active service & subscription.
- user_shop.py: Spin wheel, revoke sub, kill device, validate coupon, purchase.
- user_nodes.py: Active nodes list, IP lookup, user settings, user avatar.
- user_topup.py: Card to card, crypto (TON/USDT), Telegram Stars.
- user_support.py: Redis chat threads and admin forwarding.
- user_subscription.py: Dynamic per-protocol config parsers.
- user_speedtest.py: Low-overhead network throughput benchmarks.
"""
from bot.db.repositories.user_repo import UserRepository
from bot.web.user_profile import get_user_me, post_user_set_birthday
from bot.web.user_shop import (
    post_user_kill_device,
    post_user_purchase,
    post_user_revoke_sub,
    post_user_spin,
    post_user_validate_coupon,
)
from bot.web.user_nodes import (
    get_user_avatar,
    get_user_ip_info,
    get_user_nodes,
    post_user_settings,
)
from bot.web.user_topup import (
    get_user_topup_info,
    post_user_auto_renew,
    post_user_redeem_voucher,
    post_user_topup_card,
    post_user_topup_crypto,
    post_user_topup_crypto_check,
    post_user_topup_stars,
)
from bot.web.user_support import (
    get_user_support_messages,
    post_user_support_message,
)
from bot.web.user_subscription import (
    get_user_subscription_configs,
)
from bot.web.user_speedtest import (
    _get_speedtest_chunk,
    get_user_speedtest_payload,
    get_user_speedtest_ping,
    post_user_speedtest_upload,
)

__all__ = [
    "get_user_me",
    "post_user_set_birthday",
    "post_user_spin",
    "post_user_revoke_sub",
    "post_user_kill_device",
    "post_user_validate_coupon",
    "post_user_purchase",
    "get_user_nodes",
    "get_user_ip_info",
    "post_user_settings",
    "get_user_avatar",
    "get_user_topup_info",
    "post_user_topup_card",
    "post_user_topup_crypto",
    "post_user_topup_crypto_check",
    "post_user_topup_stars",
    "get_user_support_messages",
    "post_user_support_message",
    "get_user_subscription_configs",
    "_get_speedtest_chunk",
    "get_user_speedtest_ping",
    "get_user_speedtest_payload",
    "post_user_speedtest_upload",
    "post_user_redeem_voucher",
    "post_user_auto_renew",
]
