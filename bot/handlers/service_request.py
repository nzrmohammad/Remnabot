"""«Services» section with automatic purchase.

Decomposed modular router aggregating:
- `bot.handlers.shop_purchase`: Catalog viewing, checkout, purchase execution & receipts.
- `bot.handlers.shop_renew`: Existing account renewals, selection, and alert callbacks.
- `bot.handlers.shop_trial`: Free trial creation, custom requests, and admin fulfillment.
- `bot.handlers.shop_coupons`: Promo and coupon code application and removal.
"""
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, admin_thread_kwargs, fmt, parse_int, resolve_op
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.referral_repo import ReferralRepository
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.support_repo import SupportMessageRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.menu import delete_message_silently, render_menu
from bot.services.remnawave import RemnawaveClient
from bot.services.render import render_services
from bot.states.service_request import ServiceRequestStates

# Re-exports from sub-handlers for backward compatibility and test mock patching
from bot.handlers.shop_purchase import (
    _PURCHASE_LOCKS,
    _ensure_can_buy,
    _maybe_reward_referrer,
    _notify_admin,
    _render_buy_confirm,
    _render_purchase_result,
    buy_new_account,
    confirm_new_account,
    router as _shop_purchase_router,
    service_buy,
    service_view,
)
from bot.handlers.shop_renew import (
    _verify_account,
    buy_for_account,
    confirm_for_account,
    renew_pick_service,
    router as _shop_renew_router,
    service_choose_account,
)
from bot.handlers.shop_trial import (
    _REQUEST_DONE_NOTIFIED,
    _request_done_kb,
    request_done_notify,
    router as _shop_trial_router,
    service_new_forward,
    service_new_request,
    service_trial_username,
)
from bot.handlers.shop_coupons import (
    apply_coupon_prompt,
    process_coupon_code,
    remove_coupon,
    router as _shop_coupons_router,
)

logger = logging.getLogger(__name__)
router = Router(name="service_request")

_safe_int = parse_int
_render_services = render_services


@router.callback_query(F.data == "menu:services")
async def services_entry(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    render_services_fn = resolve_op("_render_services", render_services)
    await render_services_fn(bot, user, user_repo, session)
    await call.answer()


# Include sub-routers
router.include_router(_shop_trial_router)
router.include_router(_shop_coupons_router)
router.include_router(_shop_renew_router)
router.include_router(_shop_purchase_router)

__all__ = [
    "router",
    "services_entry",
    "_PURCHASE_LOCKS",
    "_REQUEST_DONE_NOTIFIED",
    "_safe_int",
    "_ensure_can_buy",
    "_render_services",
    "_render_buy_confirm",
    "_maybe_reward_referrer",
    "_render_purchase_result",
    "_verify_account",
    "_notify_admin",
    "renew_pick_service",
    "buy_for_account",
    "confirm_for_account",
    "buy_new_account",
    "confirm_new_account",
    "service_view",
    "service_buy",
    "service_confirm",
    "service_choose_account",
    "service_new_request",
    "service_trial_username",
    "service_new_forward",
    "request_done_notify",
    "_request_done_kb",
    "apply_coupon_prompt",
    "remove_coupon",
    "process_coupon_code",
    "render_menu",
    "delete_message_silently",
    "ServiceRepository",
    "WalletRepository",
    "UserRepository",
    "CouponRepository",
    "ReferralRepository",
    "SupportMessageRepository",
    "RemnawaveClient",
    "ServiceRequestStates",
]
