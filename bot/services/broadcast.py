"""Broadcast service: resolve broadcast audiences and manage delivery queues."""
from datetime import datetime, timezone

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Order, Wallet
from bot.db.repositories.user_repo import UserRepository
from bot.services.remnawave import RemnawaveClient


async def resolve_broadcast_recipients(
    session: AsyncSession,
    remnawave: RemnawaveClient,
    target: str,
) -> list[int]:
    """Resolve list of recipient telegram IDs based on broadcast target filter."""
    if target == "all":
        users = await UserRepository(session).all_users()
        return [u.telegram_id for u in users]

    if target == "balance":
        stmt = select(Wallet.telegram_id).where(Wallet.balance > 0)
        res = await session.execute(stmt)
        return [row[0] for row in res.fetchall()]

    if target == "buyers":
        stmt = select(distinct(Order.telegram_id)).where(Order.status == "paid")
        res = await session.execute(stmt)
        return [row[0] for row in res.fetchall()]

    # Targets requiring Remnawave
    panel_users = await remnawave.get_all_panel_users() or []
    now = datetime.now(timezone.utc)
    active_tids: set[int] = set()
    for pu in panel_users:
        if str(pu.get("status", "")).upper() == "ACTIVE":
            exp_str = pu.get("expireAt")
            if exp_str:
                try:
                    exp = datetime.fromisoformat(str(exp_str).replace("Z", "+00:00"))
                    if exp > now:
                        tid = pu.get("telegramId")
                        if tid and int(tid) > 0:
                            active_tids.add(int(tid))
                except Exception:
                    pass

    if target == "active":
        return list(active_tids)

    if target == "expired":
        all_users = await UserRepository(session).all_users()
        all_tids = {u.telegram_id for u in all_users}
        return list(all_tids - active_tids)

    users = await UserRepository(session).all_users()
    return [u.telegram_id for u in users]


_resolve_broadcast_recipients = resolve_broadcast_recipients
