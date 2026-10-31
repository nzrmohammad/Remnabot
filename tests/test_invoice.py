"""Unit and integration tests for Digital Invoice & Official Receipt System."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from bot.db.models import Order, OrderStatus, User
from bot.services.invoice_service import generate_invoice_number, get_order_invoice_data, send_invoice_to_telegram


@pytest.mark.anyio
async def test_get_order_invoice_data_and_telegram_dispatch(session_factory):
    async with session_factory() as session:
        # Create user
        user = User(telegram_id=987654321, username="test_buyer", full_name="خریدار تست", phone_number="09123456789")
        session.add(user)
        await session.flush()

        # Create paid order
        order = Order(
            telegram_id=987654321,
            service_id=1,
            service_name="بسته طلایی 50 گیگ 30 روزه",
            amount=150000,
            duration_days=30,
            traffic_gb=50,
            status=OrderStatus.PAID.value,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

        # 1. Fetch invoice data
        inv = await get_order_invoice_data(session, order.id, 987654321, store_name="تست رمنا")
        assert inv is not None
        assert inv["order_id"] == order.id
        assert "INV-" in inv["invoice_number"]
        assert inv["buyer"]["name"] == "خریدار تست"
        assert inv["buyer"]["phone"] == "09123456789"
        assert inv["item"]["title"] == "بسته طلایی 50 گیگ 30 روزه"
        assert inv["payment"]["amount_toman"] == 150000
        assert inv["payment"]["is_paid"] is True

        # 2. Strict authorization check: other user cannot fetch this invoice
        inv_unauthorized = await get_order_invoice_data(session, order.id, 111111111)
        assert inv_unauthorized is None

        # 3. Test sending invoice to Telegram
        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=True)
        sent = await send_invoice_to_telegram(mock_bot, 987654321, inv)
        assert sent is True
        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == 987654321
        assert "صورت‌حساب و فاکتور رسمی" in call_kwargs["text"]
        assert "INV-" in call_kwargs["text"]
