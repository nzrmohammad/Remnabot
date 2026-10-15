"""Tests for Infra-Billing and Server Cost Tracking features."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Base, NodeCost, Order, User
from bot.db.repositories.node_cost_repo import NodeCostRepository
from bot.services.node_monitor import check_nodes_billing_due_dates


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_node_cost_repo_crud_and_due_dates(session_factory):
    async with session_factory() as session:
        repo = NodeCostRepository(session)
        now_utc = datetime.now(timezone.utc)

        # 1. Upsert new node cost
        node1 = await repo.upsert(
            node_uuid="node-uuid-hetzner-1",
            node_id=1,
            node_name="Server Germany 1",
            provider="Hetzner",
            monthly_cost_toman=2500000,
            monthly_cost_eur=35.0,
            currency="USD",
            due_date=now_utc + timedelta(days=2),  # Due in 2 days (<= 3 days)
            notes="CX31 Hetzner VPS",
        )
        assert node1.id is not None
        assert node1.node_uuid == "node-uuid-hetzner-1"
        assert node1.monthly_cost_toman == 2500000
        assert node1.monthly_cost_eur == 35.0
        assert node1.currency == "USD"
        assert node1.alert_notified is False

        # 2. Add second node due in 15 days (> 3 days)
        node2 = await repo.upsert(
            node_uuid="node-uuid-ovh-2",
            node_id=2,
            node_name="Server France 2",
            provider="OVH",
            monthly_cost_toman=3200000,
            monthly_cost_eur=45.0,
            due_date=now_utc + timedelta(days=15),
            notes="OVH Game Server",
        )
        await session.commit()

        # 3. Check list_all
        all_nodes = await repo.list_all()
        assert len(all_nodes) == 2

        # 4. Check list_due_soon (threshold=3)
        due_soon = await repo.list_due_soon(days_threshold=3)
        assert len(due_soon) == 1
        assert due_soon[0].node_uuid == "node-uuid-hetzner-1"

        # 5. Mark alert sent
        await repo.mark_alert_sent("node-uuid-hetzner-1", True)
        await session.commit()

        # Should not be listed anymore because alert_notified is True
        due_soon_after = await repo.list_due_soon(days_threshold=3)
        assert len(due_soon_after) == 0

        # 6. If renewed (due date changed), alert_notified resets to False
        renewed_node = await repo.upsert(
            node_uuid="node-uuid-hetzner-1",
            due_date=now_utc + timedelta(days=32),
            monthly_cost_toman=2600000,
        )
        await session.commit()
        assert renewed_node.alert_notified is False
        assert renewed_node.monthly_cost_toman == 2600000


@pytest.mark.anyio
async def test_check_nodes_billing_due_dates_alert(session_factory):
    bot_mock = AsyncMock()
    now_utc = datetime.now(timezone.utc)

    # Seed node cost
    async with session_factory() as session:
        repo = NodeCostRepository(session)
        await repo.upsert(
            node_uuid="node-due-alert-1",
            node_name="Server Netherlands",
            provider="Hetzner",
            monthly_cost_toman=1800000,
            monthly_cost_eur=25.0,
            currency="USD",
            due_date=now_utc + timedelta(days=1),  # 1 day left
        )
        await session.commit()

    with patch("bot.services.node_monitor.get_settings") as mock_settings:
        mock_settings.return_value.ADMIN_IDS = [12345678]

        await check_nodes_billing_due_dates(bot_mock, session_factory)

        # Bot should have sent a notification message to admin 12345678
        assert bot_mock.send_message.called
        call_args = bot_mock.send_message.call_args[0]
        assert call_args[0] == 12345678
        msg_text = call_args[1]
        assert "هشدار موعد تمدید سرور" in msg_text
        assert "Server Netherlands" in msg_text
        assert "Hetzner" in msg_text
        assert "1,800,000 تومان" in msg_text
        assert "$25.00" in msg_text

    # Second check should not send duplicate message
    bot_mock.reset_mock()
    with patch("bot.services.node_monitor.get_settings") as mock_settings:
        mock_settings.return_value.ADMIN_IDS = [12345678]
        await check_nodes_billing_due_dates(bot_mock, session_factory)
        assert not bot_mock.send_message.called


@pytest.mark.anyio
async def test_infra_billing_route_registration():
    from bot.web.server import create_web_app

    bot = MagicMock()
    session_factory = MagicMock()
    remnawave = MagicMock()
    settings = MagicMock()
    settings.BOT_TOKEN = "123:abc"
    settings.ADMIN_IDS = [12345]

    app = create_web_app(
        bot=bot,
        session_factory=session_factory,
        remnawave=remnawave,
        settings=settings,
        is_dev=True,
    )
    registered_paths = [r.resource.canonical for r in app.router.routes() if r.resource]
    assert "/api/admin/infra/billing" in registered_paths
    assert "/api/admin/infra/node-cost" in registered_paths


@pytest.mark.anyio
async def test_admin_infra_billing_api_handlers(session_factory):
    import json
    from aiohttp.test_utils import make_mocked_request
    from bot.web.cache import FastCache
    from bot.web.routes_admin import get_admin_infra_billing, post_admin_node_cost

    now_utc = datetime.now(timezone.utc)
    async with session_factory() as session:
        user = User(telegram_id=99999, username="buyer")
        session.add(user)
        await session.flush()
        order = Order(
            telegram_id=99999,
            service_name="Test Plan",
            amount=5000000,
            status="paid",
            created_at=now_utc - timedelta(days=5),
        )
        session.add(order)
        await session.commit()

    remnawave_mock = AsyncMock()
    remnawave_mock.get_nodes.return_value = [
        {
            "uuid": "node-mock-1",
            "id": 10,
            "name": "Node Hetzner 10",
            "address": "1.2.3.4",
            "isConnected": True,
            "trafficUsedBytes": 100 * (1024**3),  # 100 GB
        }
    ]

    cache = FastCache()
    app_mock = {
        "session_factory": session_factory,
        "remnawave": remnawave_mock,
        "cache": cache,
        "bot_token": "123:abc",
        "admin_ids": [12345],
        "is_dev": True,
    }

    # 1. POST /api/admin/infra/node-cost
    post_payload = {
        "node_uuid": "node-mock-1",
        "node_id": 10,
        "node_name": "Node Hetzner 10",
        "provider": "Hetzner",
        "monthly_cost_toman": 1000000,
        "monthly_cost_eur": 15.0,
        "currency": "USD",
        "due_date": (now_utc + timedelta(days=20)).strftime("%Y-%m-%d"),
        "notes": "Fast NVMe VPS",
    }
    req_post = make_mocked_request(
        "POST",
        "/api/admin/infra/node-cost",
        headers={"content-type": "application/json"},
        app=app_mock,
    )
    req_post.json = AsyncMock(return_value=post_payload)

    with patch("bot.web.routes_admin._check_admin", return_value={"id": 12345, "is_admin": True}):
        res_post = await post_admin_node_cost(req_post)
        assert res_post.status == 200
        post_body = json.loads(res_post.text)
        assert post_body["ok"] is True
        assert post_body["data"]["monthly_cost_toman"] == 1000000

    # 2. GET /api/admin/infra/billing
    req_get = make_mocked_request("GET", "/api/admin/infra/billing", app=app_mock)
    with patch("bot.web.routes_admin._check_admin", return_value={"id": 12345, "is_admin": True}):
        res_get = await get_admin_infra_billing(req_get)
        assert res_get.status == 200
        data = json.loads(res_get.text)["data"]
        assert data["monthly_revenue_toman"] == 5000000
        assert data["total_infra_cost_toman"] == 1000000
        assert data["net_profit_toman"] == 4000000
        assert data["profit_margin_percent"] == 80.0
        assert data["total_traffic_gb"] == 100.0
        assert data["avg_cost_per_gb"] == 10000.0
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["provider"] == "Hetzner"
        assert data["nodes"][0]["cost_per_gb"] == 10000.0
        assert data["nodes"][0]["currency"] == "USD"


@pytest.mark.anyio
async def test_ssl_checker_service_and_endpoints():
    from bot.services.ssl_checker import check_domain_ssl, is_ip_address
    from bot.web.admin_infra_api import get_admin_ssl_health, post_admin_ssl_check
    from aiohttp.test_utils import make_mocked_request
    import json

    assert is_ip_address("1.1.1.1") is True
    assert is_ip_address("2001:db8::1") is True
    assert is_ip_address("example.com") is False

    # IP address check should skip
    res_ip = await check_domain_ssl("1.2.3.4")
    assert res_ip["is_ip"] is True
    assert res_ip["status"] == "skipped_ip"

    # Mock SSL inspect
    mock_ssl_res = {
        "domain": "test.vpn.com",
        "port": 443,
        "valid": True,
        "is_ip": False,
        "days_left": 45,
        "expires_at": "2026-11-30",
        "issuer": "Let's Encrypt",
        "status": "ok",
        "error": None,
    }

    with patch("bot.services.ssl_checker._check_domain_ssl_sync", return_value=mock_ssl_res):
        res = await check_domain_ssl("test.vpn.com")
        assert res["valid"] is True
        assert res["days_left"] == 45
        assert res["status"] == "ok"

    app_mock = {
        "remnawave": AsyncMock(get_nodes=AsyncMock(return_value=[{"address": "node1.example.com", "name": "Node DE"}])),
    }
    with patch("bot.web.routes_admin._check_admin", return_value={"id": 1, "is_admin": True}), \
         patch("bot.services.ssl_checker._check_domain_ssl_sync", return_value=mock_ssl_res):
        req_health = make_mocked_request("GET", "/api/admin/infra/ssl-health", app=app_mock)
        resp_health = await get_admin_ssl_health(req_health)
        assert resp_health.status == 200
        health_data = json.loads(resp_health.text)
        assert health_data["ok"] is True
        assert len(health_data["data"]) >= 1

        req_check = make_mocked_request("POST", "/api/admin/infra/ssl-check", app=app_mock)
        req_check.json = AsyncMock(return_value={"domain": "node1.example.com"})
        resp_check = await post_admin_ssl_check(req_check)
        assert resp_check.status == 200
        check_data = json.loads(resp_check.text)
        assert check_data["ok"] is True
        assert check_data["data"]["domain"] == "test.vpn.com"


