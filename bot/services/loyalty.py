"""Loyalty Tiers Service: DRY and Single Source of Truth for VIP tiers and discounts."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Order, OrderStatus

logger = logging.getLogger(__name__)

# VIP Loyalty Tiers definition (Single Source of Truth)
LOYALTY_TIERS = [
    {
        "id": "bronze",
        "name": "برنزی",
        "icon": "🥉",
        "min_spent": 0,
        "discount_percent": 0,
        "color": "amber-700",
        "badge_class": "bg-amber-700/15 text-amber-600 dark:text-amber-500 border-amber-700/30",
        "description": "سطح آغازین باشگاه مشتریان",
    },
    {
        "id": "silver",
        "name": "نقره‌ای",
        "icon": "🥈",
        "min_spent": 500_000,
        "discount_percent": 5,
        "color": "slate-300",
        "badge_class": "bg-slate-400/15 text-slate-300 border-slate-400/30",
        "description": "۵٪ تخفیف دائمی تمامی بسته‌ها",
    },
    {
        "id": "gold",
        "name": "طلایی",
        "icon": "🥇",
        "min_spent": 1_500_000,
        "discount_percent": 10,
        "color": "amber-400",
        "badge_class": "bg-amber-500/15 text-amber-500 dark:text-amber-400 border-amber-500/30",
        "description": "۱۰٪ تخفیف دائمی تمامی بسته‌ها",
    },
    {
        "id": "diamond",
        "name": "الماس",
        "icon": "💎",
        "min_spent": 4_000_000,
        "discount_percent": 15,
        "color": "cyan-400",
        "badge_class": "bg-cyan-500/15 text-cyan-500 dark:text-cyan-400 border-cyan-500/30",
        "description": "۱۵٪ تخفیف دائمی تمام خریدها + اولویت VIP",
    },
]


async def get_user_loyalty(
    session: AsyncSession,
    telegram_id: int,
    cache: Any = None,
) -> dict[str, Any]:
    """Calculate and return user loyalty tier, total spending, progress, and perks."""
    cache_key = f"loyalty:user:{telegram_id}"
    if cache and hasattr(cache, "get"):
        try:
            cached = await cache.get(cache_key)
            if cached and isinstance(cached, dict) and "tier_id" in cached:
                return cached
        except Exception as exc:
            logger.debug("Failed reading loyalty cache for %s: %s", telegram_id, exc)

    # Calculate total spent on successful orders
    spent_query = select(func.coalesce(func.sum(Order.amount), 0)).where(
        Order.telegram_id == telegram_id,
        Order.status == OrderStatus.PAID.value,
    )
    res = await session.execute(spent_query)
    total_spent = int(res.scalar() or 0)

    current_tier = LOYALTY_TIERS[0]
    next_tier = None

    for i, tier in enumerate(LOYALTY_TIERS):
        if total_spent >= tier["min_spent"]:
            current_tier = tier
            next_tier = LOYALTY_TIERS[i + 1] if i + 1 < len(LOYALTY_TIERS) else None
        else:
            break

    amount_to_next = 0
    progress_percent = 100
    if next_tier:
        needed = next_tier["min_spent"] - current_tier["min_spent"]
        current_in_tier = total_spent - current_tier["min_spent"]
        amount_to_next = max(0, next_tier["min_spent"] - total_spent)
        progress_percent = int(min(100, max(0, (current_in_tier / needed) * 100)))

    data = {
        "tier_id": current_tier["id"],
        "name": current_tier["name"],
        "icon": current_tier["icon"],
        "discount_percent": current_tier["discount_percent"],
        "color": current_tier["color"],
        "badge_class": current_tier["badge_class"],
        "description": current_tier["description"],
        "total_spent": total_spent,
        "amount_to_next": amount_to_next,
        "progress_percent": progress_percent,
        "next_tier_name": next_tier["name"] if next_tier else None,
        "next_tier_icon": next_tier["icon"] if next_tier else None,
        "next_tier_discount": next_tier["discount_percent"] if next_tier else None,
        "is_max_tier": next_tier is None,
    }

    if cache and hasattr(cache, "set"):
        try:
            await cache.set(cache_key, data, ttl_seconds=60)
        except Exception as exc:
            logger.debug("Failed setting loyalty cache for %s: %s", telegram_id, exc)

    return data


def apply_loyalty_discount(base_price: int, discount_percent: int) -> tuple[int, int]:
    """Calculate discounted price and discount amount. Returns (discount_amount, final_price)."""
    if discount_percent <= 0 or base_price <= 0:
        return 0, base_price
    pct = max(0, min(100, discount_percent))
    discount_amount = int((base_price * pct) / 100)
    final_price = max(0, base_price - discount_amount)
    return discount_amount, final_price
