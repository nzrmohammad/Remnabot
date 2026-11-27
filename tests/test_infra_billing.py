"""Tests for Infra-Billing and Server Cost Tracking features."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.db.models import Order, User
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
        await repo.upsert(
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
    import json

    from aiohttp.test_utils import make_mocked_request

    from bot.services.ssl_checker import check_domain_ssl, is_ip_address
    from bot.web.admin_infra_api import get_admin_ssl_health, post_admin_ssl_check

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


@pytest.mark.anyio
async def test_get_admin_github_releases():
    import json

    from aiohttp.test_utils import make_mocked_request

    from bot.web.admin_infra_api import get_admin_github_releases

    # 1. Forbidden when not admin
    req_unauth = make_mocked_request("GET", "/api/admin/infra/github-releases")
    with patch("bot.web.admin_infra_api._check_admin", return_value=None):
        resp_unauth = await get_admin_github_releases(req_unauth)
        assert resp_unauth.status == 403

    # 2. Success with mocked release fetch
    class MockResp:
        def __init__(self, data):
            self.status = 200
            self._data = data

        async def json(self):
            return self._data

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockSession:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, url, **kwargs):
            if "2dust/v2rayNG" in url:
                return MockResp({"tag_name": "v1.9.15"})
            return MockResp({"tag_name": "v2.5.7"})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    req_ok = make_mocked_request("GET", "/api/admin/infra/github-releases?app_id=v2rayng")
    with patch("bot.web.admin_infra_api._check_admin", return_value={"id": 1, "is_admin": True}), \
         patch("aiohttp.ClientSession", MockSession):
        resp = await get_admin_github_releases(req_ok)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["ok"] is True
        assert data["versions"]["v2rayng"] == "1.9.15"


def test_extract_github_downloads_per_platform():
    from bot.web.admin_infra_api import _extract_github_downloads

    dl_hiddify = _extract_github_downloads(
        "hiddify",
        [
            {"name": "Hiddify-Android-armeabi-v7a.apk", "browser_download_url": "https://ex/armv7.apk"},
            {"name": "Hiddify-Android-arm64.apk", "browser_download_url": "https://ex/arm64.apk"},
            {"name": "Hiddify-Windows-Setup-x64.exe", "browser_download_url": "https://ex/setup.exe"},
            {"name": "Hiddify-Windows-Portable-x64.zip", "browser_download_url": "https://ex/portable.zip"},
            {"name": "Hiddify-MacOS.dmg", "browser_download_url": "https://ex/mac.dmg"},
            {"name": "Hiddify-Linux-x64-AppImage.AppImage", "browser_download_url": "https://ex/linux.AppImage"},
            {"name": "Hiddify-Linux-x64-AppImage.AppImage.sig", "browser_download_url": "https://ex/linux.AppImage.sig"},
        ],
    )
    assert dl_hiddify["android"]["direct_url"] == "https://ex/arm64.apk"
    assert dl_hiddify["windows"]["url"] == "https://ex/setup.exe"
    assert dl_hiddify["windows"]["portable_url"] == "https://ex/portable.zip"
    assert dl_hiddify["macos"]["url"] == "https://ex/mac.dmg"
    assert dl_hiddify["linux"]["url"] == "https://ex/linux.AppImage"

    # Portable-only Windows archive (no Setup .exe) must populate portable_url only, never url (Setup)
    dl_v2rayn = _extract_github_downloads(
        "v2rayn",
        [
            {"name": "v2rayN-windows-64-SelfContained.zip", "browser_download_url": "https://ex/v2rayn-sc.zip"},
            {"name": "v2rayN-windows-64-desktop.zip", "browser_download_url": "https://ex/v2rayn-desktop.zip"},
        ],
    )
    assert dl_v2rayn["windows"].get("portable_url") is not None
    assert "url" not in dl_v2rayn["windows"]


@pytest.mark.anyio
async def test_remnawave_node_update_providers_and_restart():
    """Verify RemnawaveClient provider fetch, node patch fallbacks, and node restart."""
    from bot.services.remnawave import RemnawaveClient

    client = RemnawaveClient("https://panel.example.com", "secret-token")

    class FakeResp:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

    # 1. Providers listing
    client._client.get = AsyncMock(return_value=FakeResp(200, {
        "response": {
            "total": 1,
            "providers": [{"uuid": "prov-1", "name": "Hetzner", "login": "ops"}],
        }
    }))
    providers = await client.get_infra_providers()
    assert providers == [{"uuid": "prov-1", "name": "Hetzner", "login": "ops", "icon_url": ""}]

    # 2. update_node strips nodeConsumptionMultiplier when older panel rejects it
    patch_calls = []

    async def fake_patch(path, json=None):
        patch_calls.append((path, dict(json or {})))
        if len(patch_calls) == 1:
            return FakeResp(400, {"message": ["property nodeConsumptionMultiplier should not exist"]})
        return FakeResp(200, {"response": {"uuid": "node-1", "consumptionMultiplier": 1.5}})

    client._client.patch = fake_patch
    ok, res = await client.update_node(
        "node-1",
        {"consumptionMultiplier": 1.5, "nodeConsumptionMultiplier": 2.0, "isTrafficTrackingActive": True},
    )
    assert ok is True
    assert len(patch_calls) == 2
    assert "nodeConsumptionMultiplier" not in patch_calls[1][1]
    assert patch_calls[1][1]["consumptionMultiplier"] == 1.5

    # 3. restart_node sends forceRestart and falls back cleanly on old panel
    post_calls = []

    async def fake_post(path, json=None):
        post_calls.append((path, dict(json or {})))
        if len(post_calls) == 1:
            return FakeResp(400, {"message": "property forceRestart should not exist"})
        return FakeResp(200, {"response": {"eventSent": True}})

    client._client.post = fake_post
    ok_r, msg_r = await client.restart_node("node-1", force_restart=True)
    assert ok_r is True
    assert post_calls[0] == ("/api/nodes/node-1/actions/restart", {"forceRestart": True})
    assert post_calls[1] == ("/api/nodes/node-1/actions/restart", {})


@pytest.mark.anyio
async def test_admin_node_panel_endpoints_and_ui_fixes(session_factory):
    """Verify node panel update forwarding, validation, restart endpoint, and UI guards."""
    import json
    from pathlib import Path

    from aiohttp.test_utils import make_mocked_request

    from bot.web.admin_infra_api import (
        get_admin_infra_providers,
        post_admin_node_cost,
        post_admin_node_restart,
    )
    from bot.web.cache import FastCache
    from bot.web.server import create_web_app

    settings = MagicMock()
    settings.BOT_TOKEN = "123:abc"
    settings.ADMIN_IDS = [12345]
    app = create_web_app(
        bot=MagicMock(),
        session_factory=session_factory,
        remnawave=MagicMock(),
        settings=settings,
        cache=FastCache(),
    )
    paths = {r.resource.canonical for r in app.router.routes() if r.resource}
    assert "/api/admin/infra/providers" in paths
    assert "/api/admin/infra/node/restart" in paths

    remna = MagicMock()
    remna.get_infra_providers = AsyncMock(return_value=[{"uuid": "p-1", "name": "OVH"}])
    remna.update_node = AsyncMock(return_value=(True, {"uuid": "n-1"}))
    remna.restart_node = AsyncMock(return_value=(True, "دستور ریستارت ارسال شد"))

    cache = FastCache()
    app_state = {"session_factory": session_factory, "cache": cache, "remnawave": remna}

    with patch("bot.web.admin_infra_api._check_admin", return_value={"id": 1, "is_admin": True}):
        # Providers endpoint
        prov_req = make_mocked_request("GET", "/api/admin/infra/providers", app=app_state)
        prov_resp = await get_admin_infra_providers(prov_req)
        assert prov_resp.status == 200
        assert json.loads(prov_resp.text)["providers"] == [{"uuid": "p-1", "name": "OVH"}]

        # Reject invalid multiplier
        bad_req = make_mocked_request("POST", "/api/admin/infra/node-cost", app=app_state)
        bad_req.json = AsyncMock(return_value={"node_uuid": "n-1", "consumption_multiplier": -2})
        bad_resp = await post_admin_node_cost(bad_req)
        assert bad_resp.status == 400
        remna.update_node.assert_not_awaited()

        # Forward valid panel fields + traffic tracking options + persist local cost
        ok_req = make_mocked_request("POST", "/api/admin/infra/node-cost", app=app_state)
        ok_req.json = AsyncMock(return_value={
            "node_uuid": "n-1",
            "node_name": "Germany-01",
            "provider": "OVH",
            "provider_uuid": "p-1",
            "monthly_cost_toman": 1500000,
            "consumption_multiplier": 1.25,
            "node_consumption_multiplier": 1.5,
            "is_traffic_tracking_active": True,
            "traffic_limit_gb": 500,
            "traffic_reset_day": 15,
            "notify_percent": 85,
            "description": "Main EU Edge",
        })
        ok_resp = await post_admin_node_cost(ok_req)
        assert ok_resp.status == 200
        remna.update_node.assert_awaited_once_with(
            "n-1",
            {
                "consumptionMultiplier": 1.25,
                "nodeConsumptionMultiplier": 1.5,
                "isTrafficTrackingActive": True,
                "trafficLimitBytes": 500 * (1024 ** 3),
                "trafficResetDay": 15,
                "notifyPercent": 85,
                "description": "Main EU Edge",
                "providerUuid": "p-1",
            },
        )

        # Reject invalid reset day (> 31)
        bad_day_req = make_mocked_request("POST", "/api/admin/infra/node-cost", app=app_state)
        bad_day_req.json = AsyncMock(return_value={"node_uuid": "n-1", "traffic_reset_day": 35})
        bad_day_resp = await post_admin_node_cost(bad_day_req)
        assert bad_day_resp.status == 400

        # Restart endpoint
        rst_req = make_mocked_request("POST", "/api/admin/infra/node/restart", app=app_state)
        rst_req.json = AsyncMock(return_value={"node_uuid": "n-1", "node_name": "Germany-01", "force_restart": True})
        rst_resp = await post_admin_node_restart(rst_req)
        assert rst_resp.status == 200
        remna.restart_node.assert_awaited_once_with("n-1", force_restart=True)

    # Node/Core version extraction across modern nested & legacy flat Remnawave DTOs
    from bot.web.admin_overview_nodes import extract_node_panel_fields

    modern_meta = extract_node_panel_fields({"versions": {"nodeVersion": "2.4.1", "xrayVersion": "25.3.6"}})
    assert modern_meta["node_version"] == "2.4.1"
    assert modern_meta["xray_version"] == "25.3.6"

    legacy_meta = extract_node_panel_fields({"nodeVersion": "2.1.0", "xrayVersion": "24.12.31"})
    assert legacy_meta["node_version"] == "2.1.0"
    assert legacy_meta["xray_version"] == "24.12.31"

    # UI assertions for pulsing icon-only due badge, English %, calibrated word-spacing, 3 stacked emoji rows, and versions
    base_css = Path("bot/web/static/css/base.css").read_text(encoding="utf-8")
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    nodes_js = Path("bot/web/static/js/admin_nodes.js").read_text(encoding="utf-8")
    finance_js = Path("bot/web/static/js/admin_finance.js").read_text(encoding="utf-8")

    assert "word-spacing: 0.22em" not in base_css
    assert "word-spacing: 0.12em" not in base_css
    assert "word-spacing: 0.14em" not in base_css
    assert "پورسانت نقدی دعوت (%)" in admin_html
    assert "پورسانت نقدی دعوت (٪)" not in admin_html
    assert "پایش لحظه‌ای مصرف منابع، سرعت و کنترل نودها" not in admin_html
    assert "هاست‌ها، پروفایل Xray، اسنیپت‌ها، اسکواد خارجی و تنظیمات ساب" not in admin_html
    assert "(Config Profiles)" not in admin_html
    assert "(Config Profile)" not in admin_html
    assert "(Infra Providers)" not in admin_html
    assert 'id="refreshNodesTabBtn"' not in admin_html
    assert 'id="panelHostSquadsModal"' in admin_html
    assert 'id="panelHostsSelectAllBtn"' in admin_html
    assert 'id="nodeBillingTabBtn_due"' in admin_html
    assert 'id="nodeBillingTabPane_due"' in admin_html
    assert 'id="nodeBillingNotes"' not in admin_html
    assert 'id="panelBillCreateModal"' in admin_html
    assert admin_html.find('id="panelHostPort"') < admin_html.find('id="panelHostAddress"')
    assert admin_html.find('id="subtabBtnNodesPanel"') < admin_html.find('id="subtabBtnNodesServers"')
    assert 'id="panelHostInboundPickerModal"' in admin_html
    assert 'id="nodeConfigProfilePickerModal"' in admin_html
    assert "animate-ping" in nodes_js and "سررسید!" not in nodes_js
    assert nodes_js.count("openNodeBoxIds") == 2
    assert "$('adminOverviewNodesList') || $('adminNodesFullList')" not in nodes_js
    assert "خوانده‌شده از Infra Billing پنل\">پنل</span>" not in nodes_js
    assert "User / Node Multiplier:" not in nodes_js
    assert "ورژن هسته (Xray):" in nodes_js
    assert "ورژن نود:" in nodes_js
    assert "ضریب مصرف کاربر:" in nodes_js
    assert "ضریب مصرف سرور:" in nodes_js
    assert "ردیابی ترافیک:" in nodes_js
    assert "ریست ترافیک" in nodes_js and "غیرفعال" in nodes_js
    assert nodes_js.find("btn-reset-node-traffic") < nodes_js.find("btn-restart-node")
    assert "هزینه و تمدید:" not in admin_html
    assert "هزینه و تمدید:" not in nodes_js
    assert "titleEl.querySelector('span')" in finance_js

    panel_js = Path("bot/web/static/js/admin_panel.js").read_text(encoding="utf-8")
    admin_js = Path("bot/web/static/js/admin.js").read_text(encoding="utf-8")
    assert "window.panelCtrl?.fetchOverview" in admin_js
    assert "internalSquads" in panel_js
    assert "لغو انتخاب همه" in panel_js
    assert "sub: ''" in panel_js
    assert panel_js.find("${escapeHtml(h.remark || 'Host')}") < panel_js.rfind("${statusIcon}")
    assert "panelCtrl.openHostSquadsModal()" in admin_html
    assert panel_js.find("${inbounds.length} اینباند") < panel_js.find("${escapeHtml(p.name || 'Profile')}")
    infra_section = panel_js[panel_js.find("function renderInfraProviders"):]
    assert (
        infra_section.find('data-action="edit"') < infra_section.find("${escapeHtml(p.name || '')}")
        and "openProviderModal(" in infra_section
    )


@pytest.mark.anyio
async def test_remnawave_panel_extras_and_admin_panel_endpoints(session_factory):
    """Verify extended Remnawave panel client methods and admin_panel_api endpoints."""
    import json

    from aiohttp.test_utils import make_mocked_request

    from bot.services.remnawave import RemnawaveClient
    from bot.web.admin_panel_api import (
        get_admin_panel_control,
        post_admin_infra_bill_create,
        post_admin_infra_bill_delete,
        post_admin_infra_provider_save,
        post_admin_panel_external_squad_users,
        post_admin_panel_host_save,
        post_admin_panel_hosts_bulk,
        post_admin_panel_internal_squad_delete,
        post_admin_panel_internal_squad_save,
        post_admin_panel_node_action,
        post_admin_panel_snippet_save,
        post_admin_panel_subscription_settings,
    )
    from bot.web.cache import FastCache
    from bot.web.server import create_web_app

    client = RemnawaveClient("https://panel.example.com", "secret")

    class FakeResp:
        def __init__(self, status_code, body=None):
            self.status_code = status_code
            self._body = body
            self.content = b"1" if body is not None else b""

        def json(self):
            return self._body

    calls = []

    async def fake_request(method, path, json=None):
        calls.append((method, path, json))
        if path == "/api/tokens":
            return FakeResp(403, {"message": "Admin JWT required"})
        if path == "/api/hosts":
            return FakeResp(200, {"response": [{"uuid": "h-1", "remark": "DE", "address": "de.ex", "port": 443}]})
        if path == "/api/config-profiles":
            return FakeResp(200, {"response": {"configProfiles": [{"uuid": "cp-1", "name": "Main", "inbounds": []}]}})
        if path == "/api/snippets":
            return FakeResp(200, {"response": [{"name": "Ads", "snippet": []}]})
        if path == "/api/external-squads":
            return FakeResp(200, {"response": {"externalSquads": [{"uuid": "es-1", "name": "VIP"}]}})
        if path == "/api/internal-squads":
            return FakeResp(200, {"response": {"internalSquads": [{"uuid": "sq-1", "name": "SquadOne"}]}})
        if path == "/api/subscription-settings":
            return FakeResp(200, {"response": {"uuid": "sub-1", "profileTitle": "Store"}})
        if path == "/api/infra-billing/providers":
            return FakeResp(200, {"response": {"providers": [{"uuid": "p-1", "name": "Hetzner"}]}})
        if path == "/api/infra-billing/nodes":
            return FakeResp(200, {"response": {"nodes": [{"uuid": "bn-1", "nodeUuid": "n-1", "providerUuid": "p-1", "nextBillingAt": "2026-12-01T00:00:00Z"}]}})
        if path == "/api/infra-billing/history":
            return FakeResp(200, {"response": {"records": [{"uuid": "bill-1", "providerUuid": "p-1", "amount": 25.5, "billedAt": "2026-11-20T00:00:00Z"}]}})
        return FakeResp(200, {"response": {"ok": True}})

    client._client.request = fake_request
    client._client.get = lambda path, **kwargs: fake_request("GET", path)

    tok = await client.get_api_tokens()
    assert tok["ok"] is False and tok["jwt_required"] is True

    ok_dis, _ = await client.set_node_enabled("n-1", False)
    assert ok_dis is True and ("POST", "/api/nodes/n-1/actions/disable", {}) in calls

    ok_rst, _ = await client.restart_all_nodes(force_restart=True)
    assert ok_rst is True and ("POST", "/api/nodes/actions/restart-all", {"forceRestart": True}) in calls

    ok_bulk, _ = await client.bulk_hosts_action("enable", ["h-1"])
    assert ok_bulk is True and ("POST", "/api/hosts/bulk/enable", {"uuids": ["h-1"]}) in calls

    # Route registration + admin endpoints
    settings = MagicMock()
    settings.BOT_TOKEN = "123:abc"
    settings.ADMIN_IDS = [1]
    app = create_web_app(
        bot=MagicMock(),
        session_factory=session_factory,
        remnawave=client,
        settings=settings,
        cache=FastCache(),
    )
    paths = {r.resource.canonical for r in app.router.routes() if r.resource}
    for required_path in (
        "/api/admin/infra/node/action",
        "/api/admin/infra/node/keygen",
        "/api/admin/infra/node/create",
        "/api/admin/infra/node/delete",
        "/api/admin/infra/providers/save",
        "/api/admin/infra/providers/delete",
        "/api/admin/infra/node/sync",
        "/api/admin/infra/bills/create",
        "/api/admin/infra/bills/delete",
        "/api/admin/panel/control",
        "/api/admin/panel/hosts/save",
        "/api/admin/panel/hosts/bulk",
        "/api/admin/panel/snippets/save",
        "/api/admin/panel/snippets/delete",
        "/api/admin/panel/subscription-settings",
        "/api/admin/panel/external-squads/users",
        "/api/admin/panel/external-squads/save",
        "/api/admin/panel/external-squads/delete",
        "/api/admin/panel/internal-squads/users",
        "/api/admin/panel/internal-squads/save",
        "/api/admin/panel/internal-squads/delete",
        "/api/admin/panel/config-profiles/save",
        "/api/admin/panel/config-profiles/delete",
        "/api/admin/panel/users",
        "/api/admin/panel/tokens/create",
        "/api/admin/panel/tokens/delete",
    ):
        assert required_path in paths

    app_state = {"session_factory": session_factory, "cache": FastCache(), "remnawave": client}
    with patch("bot.web.admin_panel_api._check_admin", return_value={"id": 1, "is_admin": True}):
        ctrl_resp = await get_admin_panel_control(make_mocked_request("GET", "/api/admin/panel/control", app=app_state))
        assert ctrl_resp.status == 200
        ctrl_data = json.loads(ctrl_resp.text)["data"]
        assert len(ctrl_data["hosts"]) == 1
        assert len(ctrl_data["config_profiles"]) == 1
        assert len(ctrl_data["internal_squads"]) == 1
        assert len(ctrl_data["infra_billing_history"]) == 1
        assert isinstance(ctrl_data.get("provider_currencies"), dict)
        assert ctrl_data["api_tokens_info"]["jwt_required"] is True

        # Verify panel nextBillingAt automatically resolves due_date when local DB lacks an entry
        from bot.web.admin_overview_nodes import compute_due_metadata, extract_panel_billing_map
        pb_map = extract_panel_billing_map(ctrl_data["infra_billing_nodes"])
        _dt, p_due_str, _p_jal, _p_days, p_src = compute_due_metadata(None, datetime.now(timezone.utc), pb_map.get("n-1"))
        assert p_due_str == "2026-12-01" and p_src == "panel"

        req_bill = make_mocked_request("POST", "/api/admin/infra/bills/create", app=app_state)
        req_bill.json = AsyncMock(return_value={"provider_uuid": "p-1", "amount": 35.0, "billed_at": "2026-11-25"})
        assert (await post_admin_infra_bill_create(req_bill)).status == 200
        assert any(
            m == "POST" and p == "/api/infra-billing/history" and j and j.get("providerUuid") == "p-1" and j.get("amount") == 35.0
            for m, p, j in calls
        )

        req_bill_del = make_mocked_request("POST", "/api/admin/infra/bills/delete", app=app_state)
        req_bill_del.json = AsyncMock(return_value={"uuid": "bill-1"})
        assert (await post_admin_infra_bill_delete(req_bill_del)).status == 200

        req_act = make_mocked_request("POST", "/api/admin/infra/node/action", app=app_state)
        req_act.json = AsyncMock(return_value={"action": "reset_traffic", "node_uuid": "n-1", "node_name": "DE"})
        assert (await post_admin_panel_node_action(req_act)).status == 200

        # Internal Squads create, update & delete
        req_sq_new = make_mocked_request("POST", "/api/admin/panel/internal-squads/save", app=app_state)
        req_sq_new.json = AsyncMock(return_value={"name": "VIP-Internal", "inbounds": ["inb-1"]})
        assert (await post_admin_panel_internal_squad_save(req_sq_new)).status == 200
        assert ("POST", "/api/internal-squads", {"name": "VIP-Internal", "inbounds": ["inb-1"]}) in calls

        req_sq_edit = make_mocked_request("POST", "/api/admin/panel/internal-squads/save", app=app_state)
        req_sq_edit.json = AsyncMock(return_value={"uuid": "sq-1", "name": "VIP-Updated", "inbounds": ["inb-2"]})
        assert (await post_admin_panel_internal_squad_save(req_sq_edit)).status == 200
        assert ("PATCH", "/api/internal-squads", {"uuid": "sq-1", "name": "VIP-Updated", "inbounds": ["inb-2"]}) in calls

        req_sq_del = make_mocked_request("POST", "/api/admin/panel/internal-squads/delete", app=app_state)
        req_sq_del.json = AsyncMock(return_value={"uuid": "sq-1"})
        assert (await post_admin_panel_internal_squad_delete(req_sq_del)).status == 200
        assert ("DELETE", "/api/internal-squads/sq-1", None) in calls

        req_host = make_mocked_request("POST", "/api/admin/panel/hosts/save", app=app_state)
        req_host.json = AsyncMock(return_value={
            "uuid": "h-1",
            "remark": "DE",
            "address": "de.ex",
            "port": 443,
            "squad_mode": "ALLOW_ONLY",
            "squad_uuids": ["sq-1"],
        })
        assert (await post_admin_panel_host_save(req_host)).status == 200
        assert any(
            m == "PATCH" and p == "/api/hosts" and j and j.get("internalSquads") == {"mode": "ALLOW_ONLY", "squads": ["sq-1"]}
            for m, p, j in calls
        )

        # Verify legacy Remnawave (<v3.4) fallback converts internalSquads(EXCLUDE) -> excludedInternalSquads
        legacy_calls = []

        async def fake_legacy_request(method, path, json=None):
            legacy_calls.append((method, path, json))
            if json and "internalSquads" in json:
                return FakeResp(400, {"message": "Unknown property internalSquads"})
            return FakeResp(200, {"response": {"uuid": "h-2"}})

        client._client.request = fake_legacy_request
        ok_leg, _ = await client.create_host({
            "remark": "Legacy",
            "address": "leg.ex",
            "port": 443,
            "internalSquads": {"mode": "EXCLUDE", "squads": ["sq-1"]},
        })
        assert ok_leg is True
        assert legacy_calls[-1][2].get("excludedInternalSquads") == ["sq-1"]
        client._client.request = fake_request
        client._client.get = lambda path, **kwargs: fake_request("GET", path)

        req_bulk = make_mocked_request("POST", "/api/admin/panel/hosts/bulk", app=app_state)
        req_bulk.json = AsyncMock(return_value={"action": "disable", "uuids": ["h-1"]})
        assert (await post_admin_panel_hosts_bulk(req_bulk)).status == 200

        req_snip = make_mocked_request("POST", "/api/admin/panel/snippets/save", app=app_state)
        req_snip.json = AsyncMock(return_value={"name": "Ads", "snippet": '[{"type": "field"}]'})
        assert (await post_admin_panel_snippet_save(req_snip)).status == 200

        req_sub = make_mocked_request("POST", "/api/admin/panel/subscription-settings", app=app_state)
        req_sub.json = AsyncMock(return_value={"uuid": "sub-1", "profile_title": "Remna", "profile_update_interval": 12})
        assert (await post_admin_panel_subscription_settings(req_sub)).status == 200

        req_sq = make_mocked_request("POST", "/api/admin/panel/external-squads/users", app=app_state)
        req_sq.json = AsyncMock(return_value={"squad_uuid": "es-1", "user_uuids": ["u-1"], "action": "add"})
        assert (await post_admin_panel_external_squad_users(req_sq)).status == 200

        req_prov = make_mocked_request("POST", "/api/admin/infra/providers/save", app=app_state)
        req_prov.json = AsyncMock(return_value={"name": "Hetzner"})
        assert (await post_admin_infra_provider_save(req_prov)).status == 200

        # Panel-driven due alert when node only has nextBillingAt in Remnawave infra-billing
        from datetime import timedelta

        from bot.services.node_monitor import _PANEL_BILLING_ALERTED, check_nodes_billing_due_dates

        _PANEL_BILLING_ALERTED.clear()
        soon_iso = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
        panel_rw = AsyncMock()
        panel_rw.get_infra_billing_nodes = AsyncMock(
            return_value=[{"uuid": "bn-p", "nodeUuid": "panel-only-n1", "nextBillingAt": soon_iso, "provider": {"name": "Leaseweb"}}]
        )
        panel_rw.get_nodes = AsyncMock(return_value=[{"uuid": "panel-only-n1", "name": "FI-Panel"}])
        panel_bot = AsyncMock()
        with patch("bot.services.node_monitor.get_settings") as mock_settings:
            mock_settings.return_value.ADMIN_IDS = [123]
            await check_nodes_billing_due_dates(panel_bot, session_factory, remnawave=panel_rw)
        assert panel_bot.send_message.called
        assert _PANEL_BILLING_ALERTED.get("panel-only-n1") == soon_iso[:10]


@pytest.mark.anyio
async def test_infra_node_sync_dto_validation_and_provider_switch():
    """Ensure sync_infra_billing_node matches Remnawave DTOs and never triggers 502 on missing due_date."""
    import json

    from aiohttp.test_utils import make_mocked_request

    from bot.services.remnawave import RemnawaveClient
    from bot.web.admin_panel_api import post_admin_infra_node_sync

    client = RemnawaveClient("https://panel.example.com", "secret")

    class FakeResp:
        def __init__(self, status_code, body=None):
            self.status_code = status_code
            self._body = body
            self.content = b"1" if body is not None else b""

        def json(self):
            return self._body

    # 1. _extract_panel_error preserves detailed Zod errors alongside Validation failed
    err_detail = client._extract_panel_error(
        FakeResp(400, {"message": "Validation failed", "errors": [{"path": ["nextBillingAt"], "message": "Required"}]})
    )
    assert "Validation failed" in err_detail and "nextBillingAt: Required" in err_detail

    calls = []
    billing_nodes = [{"uuid": "bn-1", "nodeUuid": "n-1", "providerUuid": "p-1", "nextBillingAt": "2026-12-01T00:00:00.000Z"}]

    async def fake_request(method, path, json=None):
        calls.append((method, path, json))
        if method == "GET" and path == "/api/infra-billing/nodes":
            return FakeResp(200, {"response": {"nodes": billing_nodes}})
        if method == "PATCH" and path == "/api/infra-billing/nodes":
            if json and "providerUuid" in json:
                return FakeResp(400, {"message": "Validation failed"})
            return FakeResp(200, {"response": {"uuid": "bn-1"}})
        return FakeResp(200, {"response": {"uuid": "bn-new"}})

    client._client.request = fake_request

    # Same provider: PATCH must NOT send providerUuid, and preserves existing nextBillingAt when omitted
    ok, _ = await client.sync_infra_billing_node("p-1", "n-1")
    assert ok is True
    patch_calls = [c for c in calls if c[0] == "PATCH"]
    assert len(patch_calls) == 1
    assert patch_calls[0][2] == {"uuid": "bn-1", "nextBillingAt": "2026-12-01T00:00:00.000Z"}

    # Fallback to bulk `uuids` DTO if panel rejects singular `uuid`
    calls.clear()

    async def fake_bulk_patch(method, path, json=None):
        calls.append((method, path, json))
        if method == "GET":
            return FakeResp(200, {"response": {"nodes": billing_nodes}})
        if method == "PATCH" and json and "uuid" in json:
            return FakeResp(400, {"message": "uuids must be an array"})
        return FakeResp(200, {"response": {"updated": 1}})

    client._client.request = fake_bulk_patch
    ok_bulk, _ = await client.sync_infra_billing_node("p-1", "n-1", next_billing_at="2026-12-15T00:00:00.000Z")
    assert ok_bulk is True
    assert calls[-1][2] == {"uuids": ["bn-1"], "nextBillingAt": "2026-12-15T00:00:00.000Z"}

    # Different provider: DELETE old record + POST new record cleanly
    calls.clear()
    client._client.request = fake_request
    ok_switch, _ = await client.sync_infra_billing_node("p-2", "n-1", next_billing_at="2026-12-20T00:00:00.000Z")
    assert ok_switch is True
    assert ("DELETE", "/api/infra-billing/nodes/bn-1", None) in calls
    assert ("POST", "/api/infra-billing/nodes", {"providerUuid": "p-2", "nodeUuid": "n-1", "nextBillingAt": "2026-12-20T00:00:00.000Z"}) in calls

    # Unlinked node without due_date returns 400 (not 502 Error Log alert)
    billing_nodes.clear()
    app_state = {"session_factory": MagicMock(), "cache": MagicMock(), "remnawave": client}
    req_missing_due = make_mocked_request("POST", "/api/admin/infra/node/sync", app=app_state)
    req_missing_due.json = AsyncMock(return_value={"node_uuid": "n-unlinked", "provider_uuid": "p-1", "due_date": ""})
    with patch("bot.web.admin_panel_api._check_admin", return_value={"id": 1, "is_admin": True}):
        resp_missing = await post_admin_infra_node_sync(req_missing_due)
        assert resp_missing.status == 400
        assert json.loads(resp_missing.text)["ok"] is False

    # Existing linked node updated with empty clean_prov (due-date-only PATCH) must PATCH instead of DELETE+POST
    billing_nodes.append({"uuid": "bn-1", "nodeUuid": "n-1", "providerUuid": "p-1", "nextBillingAt": "2026-12-01T00:00:00.000Z"})
    calls.clear()
    client._client.request = fake_request
    ok_empty_prov, _ = await client.sync_infra_billing_node("", "n-1", next_billing_at="2027-01-10T00:00:00.000Z")
    assert ok_empty_prov is True
    assert not any(c[0] == "DELETE" for c in calls)
    assert any(c[0] == "PATCH" and c[2] == {"uuid": "bn-1", "nextBillingAt": "2027-01-10T00:00:00.000Z"} for c in calls)


@pytest.mark.anyio
async def test_post_admin_node_cost_syncs_due_date_when_provider_unchanged(session_factory):
    """Editing only due_date must sync nextBillingAt to panel without calling update_node."""
    import json
    from aiohttp.test_utils import make_mocked_request
    from bot.web.admin_infra_api import post_admin_node_cost
    from bot.web.cache import FastCache

    remna = MagicMock()
    remna.update_node = AsyncMock(return_value=(True, {"uuid": "n-1"}))
    remna.sync_infra_billing_node = AsyncMock(return_value=(True, {"uuid": "bn-1"}))

    req = make_mocked_request(
        "POST",
        "/api/admin/infra/node-cost",
        app={"session_factory": session_factory, "cache": FastCache(), "remnawave": remna},
    )
    req.json = AsyncMock(return_value={
        "node_uuid": "n-1",
        "node_name": "NL",
        "provider": "Spectraip",
        "billing_provider_uuid": "prov-1",
        "monthly_cost_toman": 1750000,
        "monthly_cost_eur": 6.6,
        "currency": "USD",
        "due_date": "2027-02-15",
    })
    with patch("bot.web.admin_infra_api._check_admin", return_value={"id": 1, "is_admin": True}):
        resp = await post_admin_node_cost(req)
        assert resp.status == 200
        body = json.loads(resp.text)
        assert body["ok"] is True
        assert body["panel_sync_ok"] is True
    remna.update_node.assert_not_awaited()
    remna.sync_infra_billing_node.assert_awaited_once_with(
        "prov-1", "n-1", next_billing_at="2027-02-15T00:00:00.000Z"
    )


@pytest.mark.anyio
async def test_post_admin_infra_bill_create_with_auto_extend_preserves_costs(session_factory):
    """Creating a bill record with extend_days extends due_date in DB & panel without zeroing costs."""
    import json
    from aiohttp.test_utils import make_mocked_request
    from bot.web.admin_panel_api import post_admin_infra_bill_create
    from bot.web.cache import FastCache

    base_due = datetime(2027, 3, 1, tzinfo=timezone.utc)
    async with session_factory() as session:
        await NodeCostRepository(session).upsert(
            node_uuid="n-ext-1",
            node_name="DE-1",
            provider="Spectraip",
            monthly_cost_toman=2500000,
            monthly_cost_eur=10.0,
            currency="USD",
            due_date=base_due,
        )
        await session.commit()

    remna = MagicMock()
    remna.create_infra_billing_record = AsyncMock(return_value=(True, {"uuid": "bill-ext-1"}))
    remna.sync_infra_billing_node = AsyncMock(return_value=(True, {"uuid": "bn-ext-1"}))

    req = make_mocked_request(
        "POST",
        "/api/admin/infra/bills/create",
        app={"session_factory": session_factory, "cache": FastCache(), "remnawave": remna},
    )
    req.json = AsyncMock(return_value={
        "provider_uuid": "prov-ext-1",
        "amount": 10.0,
        "billed_at": "2027-02-25",
        "node_uuid": "n-ext-1",
        "extend_days": 30,
        "current_due_date": "2027-03-01",
    })
    with patch("bot.web.admin_panel_api._check_admin", return_value={"id": 1, "is_admin": True}):
        resp = await post_admin_infra_bill_create(req)
        assert resp.status == 200
        body = json.loads(resp.text)
        assert body["ok"] is True
        assert body["new_due_date"] == "2027-03-31"

    remna.sync_infra_billing_node.assert_awaited_once_with(
        "prov-ext-1", "n-ext-1", next_billing_at="2027-03-31T00:00:00.000Z"
    )
    async with session_factory() as session:
        saved = await NodeCostRepository(session).get_by_uuid("n-ext-1")
        assert saved is not None
        assert saved.monthly_cost_toman == 2500000
        assert saved.currency == "USD"
        assert saved.due_date.strftime("%Y-%m-%d") == "2027-03-31"


@pytest.mark.anyio
async def test_node_traffic_quota_alert_respects_threshold_and_cooldown():
    """check_nodes_health_once sends Node Traffic Alert when used/limit >= notifyPercent once per cooldown."""
    from bot.services.node_monitor import _NODE_STATES, check_nodes_health_once

    node_id = "n-quota-test-1"
    _NODE_STATES.pop(node_id, None)
    mock_remna = MagicMock()
    mock_remna.get_nodes = AsyncMock(return_value=[{
        "id": node_id,
        "uuid": node_id,
        "name": "NL-Quota",
        "countryCode": "NL",
        "address": "1.2.3.4",
        "isConnected": True,
        "usersOnline": 12,
        "isTrafficTrackingActive": True,
        "trafficLimitBytes": 100 * (1024 ** 3),
        "trafficUsedBytes": 85 * (1024 ** 3),
        "notifyPercent": 80,
    }])

    notify_mock = AsyncMock(return_value=True)
    with patch("bot.services.node_monitor._notify_admins", notify_mock):
        await check_nodes_health_once(MagicMock(), mock_remna)
        await check_nodes_health_once(MagicMock(), mock_remna)

    try:
        assert notify_mock.await_count == 1
        sent_text = notify_mock.await_args.args[1]
        assert "Node Traffic Alert" in sent_text
        assert "85.0%" in sent_text
    finally:
        _NODE_STATES.pop(node_id, None)


@pytest.mark.anyio
async def test_node_crud_keygen_config_profile_and_squad_endpoints(session_factory):
    """Test node create/delete/keygen, config profiles CRUD, external/internal squad CRUD, user search, and provider URLs."""
    import json
    from aiohttp.test_utils import make_mocked_request
    from bot.services.remnawave import RemnawaveClient
    from bot.web.admin_infra_api import (
        get_admin_node_keygen,
        post_admin_node_create,
        post_admin_node_delete,
    )
    from bot.web.admin_panel_api import (
        get_admin_panel_users_search,
        post_admin_panel_config_profile_delete,
        post_admin_panel_config_profile_save,
        post_admin_panel_external_squad_delete,
        post_admin_panel_external_squad_save,
        post_admin_panel_internal_squad_users,
    )
    from bot.web.cache import FastCache

    client = RemnawaveClient("https://panel.example.com", "secret")
    calls = []

    class FakeResp:
        def __init__(self, status_code, body=None):
            self.status_code = status_code
            self._body = body
            self.content = b"1" if body is not None else b""

        def json(self):
            return self._body

    async def fake_request(method, path, json=None):
        calls.append((method, path, json))
        if path == "/api/keygen":
            return FakeResp(200, {"response": {"pubKey": "PUB-KEY-123"}})
        if path == "/api/infra-billing/providers":
            return FakeResp(200, {"response": {"providers": [{
                "uuid": "p-1",
                "name": "Hetzner",
                "loginUrl": "https://hetzner.cloud/login",
                "faviconLink": "https://hetzner.cloud/fav.ico",
            }]}})
        if path == "/api/internal-squads/sq-1/bulk-actions/add-many-users" and isinstance(json, dict) and "userUuids" in json:
            return FakeResp(422, {"message": "userIds array required"})
        return FakeResp(200, {"response": {"uuid": "ok-1"}})

    client._client.request = fake_request
    client._client.get = lambda path, **kwargs: fake_request("GET", path)
    client.get_all_panel_users = AsyncMock(return_value=[
        {"uuid": "u-1", "id": 101, "username": "ali_vpn", "status": "ACTIVE", "telegramId": 555001, "activeInternalSquads": [{"uuid": "sq-1"}]},
        {"uuid": "u-2", "id": 102, "username": "reza_test", "status": "ACTIVE", "telegramId": 555002, "activeInternalSquads": []},
    ])

    providers = await client.get_infra_providers()
    assert providers[0]["login"] == "https://hetzner.cloud/login"
    assert providers[0]["icon_url"] == "https://hetzner.cloud/fav.ico"

    app_state = {"session_factory": session_factory, "cache": FastCache(), "remnawave": client}
    with patch("bot.web.admin_infra_api._check_admin", return_value={"id": 1, "is_admin": True}), \
         patch("bot.web.admin_panel_api._check_admin", return_value={"id": 1, "is_admin": True}):
        r_key = await get_admin_node_keygen(make_mocked_request("GET", "/api/admin/infra/node/keygen", app=app_state))
        assert r_key.status == 200 and json.loads(r_key.text)["keygen"]["pubKey"] == "PUB-KEY-123"

        r_bad_node = make_mocked_request("POST", "/api/admin/infra/node/create", app=app_state)
        r_bad_node.json = AsyncMock(return_value={"name": "NoIP"})
        assert (await post_admin_node_create(r_bad_node)).status == 400

        r_new_node = make_mocked_request("POST", "/api/admin/infra/node/create", app=app_state)
        r_new_node.json = AsyncMock(return_value={
            "name": "DE-New",
            "address": "9.9.9.9",
            "port": 2222,
            "country_code": "de",
            "config_profile_uuid": "cp-1",
            "active_inbounds": ["inb-1"],
        })
        assert (await post_admin_node_create(r_new_node)).status == 200
        assert any(m == "POST" and p == "/api/nodes" and j["countryCode"] == "DE" for m, p, j in calls)

        r_del_node = make_mocked_request("POST", "/api/admin/infra/node/delete", app=app_state)
        r_del_node.json = AsyncMock(return_value={"node_uuid": "n-new", "node_name": "DE-New"})
        assert (await post_admin_node_delete(r_del_node)).status == 200
        assert ("DELETE", "/api/nodes/n-new", None) in calls

        r_cp_bad = make_mocked_request("POST", "/api/admin/panel/config-profiles/save", app=app_state)
        r_cp_bad.json = AsyncMock(return_value={"name": "Bad", "config": "{not-json"})
        assert (await post_admin_panel_config_profile_save(r_cp_bad)).status == 400

        r_cp_save = make_mocked_request("POST", "/api/admin/panel/config-profiles/save", app=app_state)
        r_cp_save.json = AsyncMock(return_value={"name": "Reality", "config": '{"inbounds": []}'})
        assert (await post_admin_panel_config_profile_save(r_cp_save)).status == 200
        assert any(m == "POST" and p == "/api/config-profiles" for m, p, _j in calls)

        r_cp_del = make_mocked_request("POST", "/api/admin/panel/config-profiles/delete", app=app_state)
        r_cp_del.json = AsyncMock(return_value={"uuid": "cp-1"})
        assert (await post_admin_panel_config_profile_delete(r_cp_del)).status == 200
        assert ("DELETE", "/api/config-profiles/cp-1", None) in calls

        r_ext_save = make_mocked_request("POST", "/api/admin/panel/external-squads/save", app=app_state)
        r_ext_save.json = AsyncMock(return_value={"name": "ExtVIP"})
        assert (await post_admin_panel_external_squad_save(r_ext_save)).status == 200
        assert any(m == "POST" and p == "/api/external-squads" for m, p, _j in calls)

        r_ext_del = make_mocked_request("POST", "/api/admin/panel/external-squads/delete", app=app_state)
        r_ext_del.json = AsyncMock(return_value={"uuid": "es-1"})
        assert (await post_admin_panel_external_squad_delete(r_ext_del)).status == 200
        assert ("DELETE", "/api/external-squads/es-1", None) in calls

        r_int_u = make_mocked_request("POST", "/api/admin/panel/internal-squads/users", app=app_state)
        r_int_u.json = AsyncMock(return_value={
            "squad_uuid": "sq-1",
            "action": "add",
            "user_refs": [{"uuid": "u-1", "id": 101}],
        })
        assert (await post_admin_panel_internal_squad_users(r_int_u)).status == 200
        assert ("POST", "/api/internal-squads/sq-1/bulk-actions/add-many-users", {"userIds": [101]}) in calls

        r_search = await get_admin_panel_users_search(
            make_mocked_request("GET", "/api/admin/panel/users?q=ali", app=app_state)
        )
        assert r_search.status == 200
        users_found = json.loads(r_search.text)["users"]
        assert len(users_found) == 1 and users_found[0]["username"] == "ali_vpn"


@pytest.mark.anyio
async def test_pick_checkhost_nodes_prioritizes_real_iran_probes():
    """_pick_checkhost_nodes selects genuine Iran (`ir*`) Check-Host probes before global probes."""
    from bot.web.admin_infra_api import _CHECKHOST_NODES_CACHE, _pick_checkhost_nodes

    _CHECKHOST_NODES_CACHE["ts"] = 0.0
    _CHECKHOST_NODES_CACHE["nodes"] = {}

    class _FakeNR:
        status = 200

        async def json(self):
            return {
                "nodes": {
                    "us1.node.check-host.net": ["us", "USA", "LA"],
                    "de1.node.check-host.net": ["de", "Germany", "Frankfurt"],
                    "ir1.node.check-host.net": ["ir", "Iran", "Tehran"],
                    "ir3.node.check-host.net": ["ir", "Iran", "Shiraz"],
                    "nl1.node.check-host.net": ["nl", "Netherlands", "Amsterdam"],
                }
            }

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    fake_sess = MagicMock()
    fake_sess.get = MagicMock(return_value=_FakeNR())
    try:
        picked = await _pick_checkhost_nodes(fake_sess, 4)
        assert picked[:2] == ["ir1.node.check-host.net", "ir3.node.check-host.net"]
        assert "de1.node.check-host.net" in picked
        assert len(picked) == 4
    finally:
        _CHECKHOST_NODES_CACHE["ts"] = 0.0
        _CHECKHOST_NODES_CACHE["nodes"] = {}





