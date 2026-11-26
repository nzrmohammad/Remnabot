"""Regression tests for Mini App UX, cache invalidation, invoice image delivery, and custom username fixes."""
import base64
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import BufferedInputFile, Contact
from aiogram.types import User as TgUser
from aiohttp.test_utils import make_mocked_request

from bot.db.models import Order, OrderStatus, Service, Topup, User, Wallet
from bot.db.repositories.user_repo import UserRepository
from bot.services.purchases import validate_panel_username
from bot.web.cache import FastCache

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.anyio
async def test_custom_username_validation_and_purchase_in_tma(session_factory):
    """Validate format/availability checks and custom_username provisioning on purchase endpoints."""
    from bot.web.user_shop import post_user_custom_plan_purchase, post_user_purchase

    assert validate_panel_username("  ali_vpn_1  ") == ("ali_vpn_1", None)
    assert validate_panel_username("ab") == (None, "username_invalid")
    assert validate_panel_username("ali vpn!") == (None, "username_invalid")

    tid = 918273
    async with session_factory() as session:
        session.add(User(telegram_id=tid, username="buyer_u"))
        session.add(Wallet(telegram_id=tid, balance=600_000))
        session.add(Service(id=601, name="Pro 30GB", price=100_000, duration_days=30, traffic_gb=30, is_active=True))
        await session.commit()

    remnawave = AsyncMock()
    remnawave.get_users_by_telegram_id.return_value = []
    remnawave.get_internal_squads.return_value = []
    remnawave.get_user_by_username.return_value = None
    remnawave.create_user.return_value = {"id": 501, "username": "ali_vpn_1", "subscriptionUrl": "https://sub/501"}

    app = {
        "session_factory": session_factory,
        "remnawave": remnawave,
        "bot": None,
        "settings": SimpleNamespace(TIMEZONE="Asia/Tehran"),
        "cache": FastCache(redis_client=None),
    }

    # 1. Invalid username rejected cleanly before touching wallet/panel
    req_bad = make_mocked_request("POST", "/api/user/purchase", app=app)
    req_bad.json = AsyncMock(return_value={"service_id": 601, "custom_username": "x!"})
    req_bad["user"] = {"id": tid, "username": "buyer_u"}
    resp_bad = await post_user_purchase(req_bad)
    assert resp_bad.status == 400
    assert json.loads(resp_bad.text)["error"] == "username_invalid"
    remnawave.create_user.assert_not_awaited()

    # 2. Taken username rejected cleanly
    remnawave.get_user_by_username.return_value = {"id": 999, "username": "taken_vpn", "status": "ACTIVE"}
    req_taken = make_mocked_request("POST", "/api/user/purchase", app=app)
    req_taken.json = AsyncMock(return_value={"service_id": 601, "custom_username": "taken_vpn"})
    req_taken["user"] = {"id": tid, "username": "buyer_u"}
    resp_taken = await post_user_purchase(req_taken)
    assert resp_taken.status == 400
    assert json.loads(resp_taken.text)["error"] == "username_taken"
    remnawave.create_user.assert_not_awaited()

    # 3. Valid available username provisions exact panel username
    remnawave.get_user_by_username.return_value = None
    req_ok = make_mocked_request("POST", "/api/user/purchase", app=app)
    req_ok.json = AsyncMock(return_value={"service_id": 601, "custom_username": "ali_vpn_1"})
    req_ok["user"] = {"id": tid, "username": "buyer_u"}
    resp_ok = await post_user_purchase(req_ok)
    assert resp_ok.status == 200
    data_ok = json.loads(resp_ok.text)
    assert data_ok["panel_username"] == "ali_vpn_1"
    assert isinstance(data_ok.get("order_id"), int)
    assert remnawave.create_user.call_args.kwargs["username"] == "ali_vpn_1"

    # 4. Custom plan purchase also honours custom_username when create_new=True
    remnawave.create_user.reset_mock()
    remnawave.create_user.return_value = {"id": 502, "username": "custom_ali", "subscriptionUrl": "https://sub/502"}
    req_custom = make_mocked_request("POST", "/api/user/custom-plan/purchase", app=app)
    req_custom.json = AsyncMock(
        return_value={
            "traffic_gb": 20,
            "duration_days": 30,
            "hwid_limit": 2,
            "create_new": True,
            "custom_username": "custom_ali",
        }
    )
    req_custom["user"] = {"id": tid, "username": "buyer_u"}
    resp_custom = await post_user_custom_plan_purchase(req_custom)
    assert resp_custom.status == 200
    assert remnawave.create_user.call_args.kwargs["username"] == "custom_ali"


@pytest.mark.anyio
async def test_post_user_claim_gift_has_no_nameerror(session_factory):
    """Ensure gift claiming endpoint works without unbound custom_username variable."""
    from bot.web.user_shop import post_user_claim_gift

    app = {
        "session_factory": session_factory,
        "remnawave": AsyncMock(),
        "bot": None,
        "settings": SimpleNamespace(TIMEZONE="Asia/Tehran"),
        "cache": FastCache(redis_client=None),
    }
    req = make_mocked_request("POST", "/api/user/gifts/claim", app=app)
    req.json = AsyncMock(return_value={"code": "NONEXISTENT"})
    req["user"] = {"id": 512345, "username": "gift_u"}
    with patch("bot.web.user_shop.enforce_invite_only", AsyncMock(return_value=None)):
        resp = await post_user_claim_gift(req)
    assert resp.status == 400
    assert json.loads(resp.text)["ok"] is False


@pytest.mark.anyio
async def test_get_user_me_exposes_service_purchase_capacity(session_factory):
    """Shop plans with max_purchases report purchases_count and remaining_purchases in /api/user/me."""
    from bot.web.user_profile import get_user_me

    tid = 817263
    async with session_factory() as session:
        session.add(User(telegram_id=tid, username="cap_u"))
        session.add(Wallet(telegram_id=tid, balance=100_000))
        session.add(
            Service(
                id=602,
                name="Limited 5x",
                price=50_000,
                duration_days=30,
                traffic_gb=20,
                max_purchases=5,
                purchases_count=2,
                is_active=True,
            )
        )
        await session.commit()

    remnawave = AsyncMock()
    remnawave.get_users_by_telegram_id.return_value = []
    remnawave.get_internal_squads.return_value = []

    app = {
        "session_factory": session_factory,
        "remnawave": remnawave,
        "settings": SimpleNamespace(TIMEZONE="Asia/Tehran"),
        "cache": FastCache(redis_client=None),
    }
    req = make_mocked_request("GET", "/api/user/me", app=app)
    req["user"] = {"id": tid, "username": "cap_u", "is_admin": False}
    resp = await get_user_me(req)
    assert resp.status == 200
    payload = json.loads(resp.text)["data"]
    limited = next(p for p in payload["plans"] if p["id"] == 602)
    assert limited["max_purchases"] == 5
    assert limited["purchases_count"] == 2
    assert limited["remaining_purchases"] == 3


@pytest.mark.anyio
async def test_send_invoice_to_telegram_sends_png_photo_and_handles_invalid_fallback(session_factory):
    """Invoice endpoint sends generated PNG image into Telegram chat and safely falls back on invalid image."""
    from bot.web.user_shop import post_user_send_invoice_telegram

    tid = 716253
    async with session_factory() as session:
        session.add(User(telegram_id=tid, username="inv_u"))
        order = Order(
            id=701,
            telegram_id=tid,
            service_name="Gold Plan",
            amount=120_000,
            status=OrderStatus.PAID.value,
        )
        session.add(order)
        await session.commit()

    bot = MagicMock()
    bot.send_photo = AsyncMock()
    bot.send_message = AsyncMock()
    app = {"session_factory": session_factory, "bot": bot, "cache": FastCache(redis_client=None)}

    data_uri = "data:image/png;base64," + base64.b64encode(_TINY_PNG).decode("ascii")
    req = make_mocked_request("POST", "/api/user/invoice/701/send-telegram", match_info={"order_id": "701"}, app=app)
    req.json = AsyncMock(return_value={"image_base64": data_uri})
    req["user"] = {"id": tid, "username": "inv_u"}

    resp = await post_user_send_invoice_telegram(req)
    assert resp.status == 200
    bot.send_photo.assert_awaited_once()
    photo_arg = bot.send_photo.call_args.kwargs["photo"]
    assert isinstance(photo_arg, BufferedInputFile)
    assert photo_arg.data == _TINY_PNG
    bot.send_message.assert_not_awaited()

    # Non-PNG payload falls back safely to formatted text invoice
    bot.send_photo.reset_mock()
    req_bad_img = make_mocked_request("POST", "/api/user/invoice/701/send-telegram", match_info={"order_id": "701"}, app=app)
    req_bad_img.json = AsyncMock(return_value={"image_base64": "not-valid-base64!!!"})
    req_bad_img["user"] = {"id": tid, "username": "inv_u"}
    resp_fallback = await post_user_send_invoice_telegram(req_bad_img)
    assert resp_fallback.status == 200
    bot.send_message.assert_awaited_once()
    bot.send_photo.assert_not_awaited()


@pytest.mark.anyio
async def test_phone_verify_and_topup_approval_invalidate_caches_and_support_refresh(session_factory):
    """Contact verification and topup approval invalidate TMA caches, and topup_info honors ?refresh=1."""
    from bot.handlers.start import handle_user_contact
    from bot.services.topups import decide_topup
    from bot.web.user_topup import get_user_topup_info

    tid = 615243
    cache = FastCache(redis_client=None)
    await cache.set(f"tma:user:{tid}:topup_info", {"ok": True, "is_phone_verified": False}, ttl_seconds=60)
    await cache.set(f"tma:user:{tid}:dashboard:default", {"ok": True}, ttl_seconds=60)

    async with session_factory() as session:
        session.add(User(telegram_id=tid, username="phone_u"))
        session.add(Wallet(telegram_id=tid, balance=10_000))
        topup = Topup(telegram_id=tid, amount=50_000, status="pending", receipt_hash="text:123")
        session.add(topup)
        await session.commit()
        topup_id = topup.id

    bot = MagicMock()
    bot.cache = cache
    bot.send_message = AsyncMock()
    bot.get_me = AsyncMock(return_value=SimpleNamespace(username="test_bot"))

    # 1. Sharing phone clears TMA caches
    msg = MagicMock()
    msg.from_user = TgUser(id=tid, is_bot=False, first_name="Ali", username="phone_u")
    msg.contact = Contact(phone_number="+989121112233", first_name="Ali", user_id=tid)
    msg.chat = SimpleNamespace(id=tid)
    msg.answer = AsyncMock()

    async with session_factory() as session:
        user_repo = UserRepository(session)
        await handle_user_contact(msg, bot, user_repo, session)

    assert await cache.get(f"tma:user:{tid}:topup_info") is None
    assert await cache.get(f"tma:user:{tid}:dashboard:default") is None

    # 2. Stale topup_info cache bypassed when ?refresh=1
    await cache.set(f"tma:user:{tid}:topup_info", {"ok": True, "is_phone_verified": False}, ttl_seconds=60)
    app = {"session_factory": session_factory, "cache": cache}
    req_fresh = make_mocked_request("GET", "/api/user/topup_info?refresh=1", app=app)
    req_fresh["user"] = {"id": tid, "username": "phone_u"}
    resp_fresh = await get_user_topup_info(req_fresh)
    assert resp_fresh.status == 200
    assert json.loads(resp_fresh.text)["is_phone_verified"] is True

    # 3. Approving topup clears cached dashboard so Mini App reload/poll gets fresh balance
    await cache.set(f"tma:user:{tid}:dashboard:default", {"stale": True}, ttl_seconds=60)
    async with session_factory() as session:
        ok, _ = await decide_topup(bot, session, topup_id, approved=True, admin_id=1, cache=cache)
        assert ok is True
        await session.commit()
    assert await cache.get(f"tma:user:{tid}:dashboard:default") is None


def test_frontend_ux_and_speedtest_fixes_present():
    """Verify HTML/CSS/JS invariants for badges accordion, avatar egg, wheel fit, speedtest, and topup/sync hooks."""
    html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    css = Path("bot/web/static/css/components.css").read_text(encoding="utf-8")
    wheel_js = Path("bot/web/static/js/wheel.js").read_text(encoding="utf-8")
    speedtest_js = Path("bot/web/static/js/speedtest.js").read_text(encoding="utf-8")
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")

    # 1 & 2. Collapsible achievements + avatar Easter Egg
    assert 'id="toggleProfileBadgesBtn"' in html
    assert 'id="profileBadgesBody" class="hidden' in html
    assert 'id="profileBadgeDetailDesc" class="hidden text-[11px] t-muted' in html
    assert 'id="profileAvatarBtn"' in html and "triggerLogoEasterEgg" in html
    assert 'setupAccordion(\'toggleProfileBadgesBtn\', \'profileBadgesBody\', \'profileBadgesChevron\')' in app_js

    # 3 & 4. Invoice image chat send + speedtest multi-stream same-server accuracy
    assert "_deliverCanvasCardToChatOrDownload" in app_js
    assert "/api/user/speedtest/payload" in speedtest_js
    assert "downloadStreamWithFallback" in speedtest_js
    assert "createRandomBuffer(524288)" in speedtest_js

    # 5. Lucky Wheel center button fit
    assert "white-space: normal;" in css
    assert "نیاز به<br/>اشتراک" in wheel_js

    # 6, 7, 8, 9. Phone unlock, live wallet sync, custom username, limited capacity badge
    assert 'id="checkoutCustomUsernameInput"' in html
    assert "limitedStockBlock" in shop_js
    assert "window.refreshTopupModalState" in wallet_js
    assert "window.unlockTopupPhoneVerificationUI" in wallet_js
    assert "_schedulePhoneVerifySync" in app_js
    assert "setupLiveSyncListeners" in app_js
    assert "window.markAwaitingTopupSync" in app_js


def test_admin_health_sub_and_redesigned_modals():
    """Verify Admin health accordion/title, full-width sub copy box, and redesigned plan/node billing modals."""
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    nodes_js = Path("bot/web/static/js/admin_nodes.js").read_text(encoding="utf-8")
    plans_js = Path("bot/web/static/js/admin_plans.js").read_text(encoding="utf-8")
    users_js = Path("bot/web/static/js/admin_users.js").read_text(encoding="utf-8")

    # Health card title simplified + collapsible accordion
    health_start = admin_html.find('id="adminSystemHealthCard"')
    health_end = admin_html.find('id="subtabContentNodesSsl"', health_start)
    health_block = admin_html[health_start:health_end]
    assert "<span>سلامت سیستم</span>" in health_block
    assert "آشتی حسابداری (Reconcile)" not in health_block
    assert 'id="runAdminReconcileBtn"' not in health_block
    assert 'id="refreshSystemHealthBtn"' not in health_block
    assert 'id="toggleSystemHealthBtn"' in health_block
    assert 'id="systemHealthChevron"' in health_block
    assert 'id="adminSystemHealthBody" class="hidden' in health_block
    assert "window.toggleSystemHealthAccordion" in nodes_js

    # Sub link modal full-width box with copy icon on right side
    sub_start = admin_html.find('id="subModal"')
    sub_end = admin_html.find('id="planModal"', sub_start)
    sub_block = admin_html[sub_start:sub_end]
    assert 'id="subModalInput"' in sub_block and "w-full" in sub_block and "pr-10" in sub_block
    assert "absolute right-2 top-1/2 -translate-y-1/2" in sub_block
    assert "$('subModalTitleText') || $('subModalTitle')" in users_js

    # Plan modal & Node billing modal redesign + theme-safe toggles + Remnawave node controls
    plan_block = admin_html[admin_html.find('id="planModal"'):admin_html.find('id="couponModal"')]
    assert 'max-w-[400px]' in plan_block
    assert 'class="sr-only switch-checkbox" id="planModalActive" checked' in plan_block
    assert "t-muted hover:t-main" in plans_js
    assert "<span>ذخیره تعرفه</span>" in plans_js

    billing_block = admin_html[admin_html.find('id="nodeBillingModal"'):admin_html.find('id="campaignDetailModal"')]
    assert 'w-[124px]' in billing_block
    assert 'grid-cols-1 sm:grid-cols-2 gap-2.5' in billing_block
    assert 'grid-cols-2 gap-2.5' in billing_block
    assert 'min-w-0' in billing_block
    assert 'تنظیمات سرور' in billing_block
    assert 'id="nodeBillingTabBtn_finance"' in billing_block
    assert 'id="nodeBillingTabBtn_due"' in billing_block
    assert 'id="nodeBillingTabBtn_panel"' in billing_block
    assert 'id="nodeBillingUserMultiplier"' in billing_block
    assert 'id="nodeBillingNodeMultiplier"' in billing_block
    assert 'id="nodeBillingTrafficTracking"' in billing_block
    assert 'id="nodeTrafficTrackingOptions"' in billing_block
    assert 'id="nodeBillingTrafficLimitGb"' in billing_block
    assert 'id="nodeBillingTrafficResetDay"' in billing_block
    assert 'id="nodeBillingNotifyPercent"' in billing_block
    assert 'id="nodeBillingConfigProfileSelect"' in billing_block
    assert 'id="nodeBillingProviderPickerBtn"' in billing_block
    assert 'id="nodeProviderPickerModal"' in billing_block
    assert 'id="nodeBillingPanelDescription"' in billing_block
    restart_block = admin_html[admin_html.find('id="restartNodeConfirmModal"'):admin_html.find('id="panelHostEditorModal"')]
    assert 'id="restartModeOptSoft"' in restart_block
    assert 'id="restartModeOptForce"' in restart_block
    assert 'انصراف' not in restart_block
    assert 'id="subtabBtnNodesPanel"' in admin_html
    assert 'id="subtabContentNodesPanel"' in admin_html
    assert "t-muted hover:t-main" in nodes_js

