"""Repository for discount / promo coupons."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Coupon, CouponUsage


class CouponRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        code: str,
        discount_percent: int = 0,
        discount_amount: int = 0,
        max_uses: int = 0,
        expires_at: datetime | None = None,
    ) -> Coupon:
        coupon = Coupon(
            code=code.strip().upper(),
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            max_uses=max_uses,
            expires_at=expires_at,
            is_active=True,
        )
        self.session.add(coupon)
        await self.session.flush()
        return coupon

    async def get_by_code(self, code: str) -> Coupon | None:
        clean = code.strip().upper()
        result = await self.session.execute(
            select(Coupon).where(Coupon.code == clean)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, coupon_id: int) -> Coupon | None:
        result = await self.session.execute(
            select(Coupon).where(Coupon.id == coupon_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Coupon]:
        result = await self.session.execute(
            select(Coupon).order_by(Coupon.id.desc())
        )
        return list(result.scalars().all())

    async def toggle_active(self, coupon: int | Coupon) -> bool:
        if isinstance(coupon, int):
            c = await self.get_by_id(coupon)
        else:
            c = coupon
        if c:
            c.is_active = not c.is_active
            await self.session.flush()
            return c.is_active
        return False

    async def delete(self, coupon: int | Coupon) -> None:
        if isinstance(coupon, int):
            c = await self.get_by_id(coupon)
        else:
            c = coupon
        if c:
            await self.session.delete(c)
            await self.session.flush()

    async def has_user_used(self, coupon_id: int, telegram_id: int) -> bool:
        result = await self.session.execute(
            select(func.count(CouponUsage.id)).where(
                CouponUsage.coupon_id == coupon_id,
                CouponUsage.telegram_id == telegram_id,
            )
        )
        return int(result.scalar_one()) > 0

    async def record_usage(
        self,
        coupon: int | Coupon,
        telegram_id: int,
        order_id: int | None = None,
        discount_applied: int = 0,
    ) -> CouponUsage:
        if isinstance(coupon, Coupon):
            coupon_obj = coupon
        else:
            coupon_obj = await self.get_by_id(coupon)
        if coupon_obj:
            coupon_obj.used_count += 1
        usage = CouponUsage(
            coupon_id=coupon_obj.id if coupon_obj else (coupon if isinstance(coupon, int) else None),
            telegram_id=telegram_id,
            order_id=order_id,
            discount_applied=discount_applied,
        )
        self.session.add(usage)
        await self.session.flush()
        return usage

    async def get_usages(self, coupon_id: int) -> list[CouponUsage]:
        """List all usages of a coupon ordered by most recent."""
        result = await self.session.execute(
            select(CouponUsage)
            .where(CouponUsage.coupon_id == coupon_id)
            .order_by(CouponUsage.id.desc())
        )
        return list(result.scalars().all())

    async def validate_coupon(
        self, code: str, telegram_id: int, price: int = 0
    ) -> tuple[bool, str | None, int]:
        """Validate coupon. Returns (is_valid, error_code, discount_amount)."""
        coupon = await self.get_by_code(code)
        if coupon is None:
            return False, "coupon_not_found", 0
        if not coupon.is_active:
            return False, "coupon_inactive", 0
        if coupon.expires_at and coupon.expires_at < datetime.now(timezone.utc):
            return False, "coupon_expired", 0
        if coupon.max_uses and coupon.max_uses > 0 and coupon.used_count >= coupon.max_uses:
            return False, "coupon_limit_reached", 0
        if await self.has_user_used(coupon.id, telegram_id):
            return False, "coupon_already_used", 0

        # Calculate discount amount
        if coupon.discount_percent and coupon.discount_percent > 0:
            discount = int(price * coupon.discount_percent / 100) if price > 0 else 0
        else:
            discount = coupon.discount_amount or 0
        if price > 0:
            discount = min(discount, price)

        return True, None, discount
