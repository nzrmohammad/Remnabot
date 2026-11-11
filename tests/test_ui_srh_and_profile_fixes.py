"""Tests for SRH user isolation & requestAt, admin user profile editing, and UI polish items."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from bot.db.repositories.user_repo import UserRepository
from bot.services.remnawave import RemnawaveClient
from bot.web.admin_users_actions import post_admin_update_user_profile
from bot.web.admin_users_detail import get_admin_user_srh
from bot.web.cache import FastCache


@pytest.mark.anyio
async def test_remnawave_get_user_srh_prevents_cross_user_leak():
    """Global /api/subscription-request-history ignoring query params must never leak another user's Streisand records."""
    client = RemnawaveClient.__new__(RemnawaveClient)
    target_uuid = "11111111-1111-1111-1111-111111111111"
    other_uuid = "22222222-2222-2222-2222-222222222222"

    async def fake_get(path, params=None):
        resp = MagicMock()
        if path == "/api/subscription-request-history":
            resp.status_code = 200
            resp.json.return_value = {
                "response": {
                    "records": [
                        {
                            "userUuid": other_uuid,
                            "userAgent": "Streisand/1.9.2",
                            "requestIp": "5.5.5.5",
                            "requestAt": "2026-11-11T10:00:00Z",
                        }
                    ]
                }
            }
            return resp
        resp.status_code = 404
        return resp

    client._client = MagicMock()
    client._client.get = AsyncMock(side_effect=fake_get)

    # Target user has NO records; must get [] instead of other user's Streisand record
    records = await client.get_user_srh(42, user_uuid=target_uuid, size=50)
    assert records == []

    # Target user HAS one record mixed with another user's record; only target's is returned
    async def fake_get_mixed(path, params=None):
        resp = MagicMock()
        if path == "/api/subscription-request-history":
            resp.status_code = 200
            resp.json.return_value = {
                "response": {
                    "records": [
                        {
                            "userUuid": other_uuid,
                            "userAgent": "Streisand/1.9.2",
                            "requestIp": "5.5.5.5",
                            "requestAt": "2026-11-11T10:00:00Z",
                        },
                        {
                            "userUuid": target_uuid,
                            "userAgent": "v2rayNG/1.8.5",
                            "requestIp": "9.9.9.9",
                            "requestAt": "2026-11-11T09:30:00Z",
                        },
                    ]
                }
            }
            return resp
        resp.status_code = 404
        return resp

    client._client.get = AsyncMock(side_effect=fake_get_mixed)
    filtered = await client.get_user_srh(42, user_uuid=target_uuid, size=50)
    assert len(filtered) == 1
    assert filtered[0]["userAgent"] == "v2rayNG/1.8.5"


@pytest.mark.anyio
async def test_remnawave_get_user_srh_empty_user_endpoint_stops_fallback():
    """If user-specific SRH endpoint explicitly returns empty [], do not fall back to global."""
    client = RemnawaveClient.__new__(RemnawaveClient)
    target_uuid = "11111111-1111-1111-1111-111111111111"
    called_paths = []

    async def fake_get(path, params=None):
        called_paths.append(path)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"response": {"records": []}}
        return resp

    client._client = MagicMock()
    client._client.get = AsyncMock(side_effect=fake_get)

    records = await client.get_user_srh(42, user_uuid=target_uuid, size=50)
    assert records == []
    assert called_paths == [f"/api/users/{target_uuid}/subscription-request-history"]


@pytest.mark.anyio
async def test_admin_user_srh_parses_request_at_and_ignores_null_param():
    """get_admin_user_srh must parse requestAt and ignore literal 'null' user_id query params."""
    mock_remna = MagicMock()
    mock_remna.get_users_by_telegram_id = AsyncMock(return_value=[{"id": 77, "uuid": "uuid-77"}])
    mock_remna.get_user_srh = AsyncMock(return_value=[
        {
            "userUuid": "uuid-77",
            "requestIp": "185.10.10.10",
            "userAgent": "Happ/2.1.0",
            "requestAt": "2026-11-10T12:30:00Z",
        }
    ])

    app = web.Application()
    app["remnawave"] = mock_remna

    req = make_mocked_request("GET", "/api/admin/user/srh?telegram_id=555&user_id=null", app=app)
    with patch("bot.web.admin_users_detail._check_admin", return_value={"id": 1, "is_admin": True}):
        resp = await get_admin_user_srh(req)

    assert resp.status == 200
    payload = json.loads(resp.text)
    assert payload["ok"] is True
    assert len(payload["data"]) == 1
    item = payload["data"][0]
    assert item["request_at"] == "2026-11-10T12:30:00Z"
    assert item["date_str"] != "—"
    assert item["relative_time"] != "—"
    mock_remna.get_user_srh.assert_awaited_once_with("77", user_uuid="uuid-77", size=50)


@pytest.mark.anyio
async def test_admin_update_user_profile_and_validation(session_factory):
    """Admin can edit user's full_name, phone_number, and birth_date from inspector, including duplicate/date guards."""
    async with session_factory() as session:
        u_repo = UserRepository(session)
        await u_repo.get_or_create(8801, "user_one", "User One")
        u2 = await u_repo.get_or_create(8802, "user_two", "User Two")
        u2.phone_number = "09120000002"
        await session.commit()

    app = web.Application()
    app["session_factory"] = session_factory
    app["cache"] = FastCache(redis_client=None)

    def _make_req(body: dict):
        req = make_mocked_request("POST", "/api/admin/user/profile", app=app)
        req.json = AsyncMock(return_value=body)
        return req

    # Non-admin rejected
    with patch("bot.web.admin_users_actions._check_admin", return_value=None):
        r_forbid = await post_admin_update_user_profile(_make_req({"telegram_id": 8801}))
        assert r_forbid.status == 403

    with patch("bot.web.admin_users_actions._check_admin", return_value={"id": 1, "is_admin": True}):
        # Invalid Jalali birth date rejected
        r_bad_bday = await post_admin_update_user_profile(
            _make_req({"telegram_id": 8801, "birth_date": "1375/12/31"})
        )
        assert r_bad_bday.status == 400

        # Duplicate phone number rejected
        r_dup_phone = await post_admin_update_user_profile(
            _make_req({"telegram_id": 8801, "phone_number": "09120000002"})
        )
        assert r_dup_phone.status == 409

        # Valid update succeeds (including Persian digits normalization)
        r_ok = await post_admin_update_user_profile(
            _make_req({
                "telegram_id": 8801,
                "full_name": "علی رضایی",
                "phone_number": "۰۹۱۲۱۱۱۱۱۱۱",
                "birth_date": "۱۳۷۵/۰۷/۲۲",
            })
        )
        assert r_ok.status == 200
        data_ok = json.loads(r_ok.text)
        assert data_ok["ok"] is True
        assert data_ok["user"]["full_name"] == "علی رضایی"
        assert data_ok["user"]["phone_number"] == "09121111111"
        assert data_ok["user"]["birth_date"] == "1375/07/22"

    async with session_factory() as session:
        refreshed = await UserRepository(session).get_by_telegram_id(8801)
        assert refreshed is not None
        assert refreshed.full_name == "علی رضایی"
        assert refreshed.phone_number == "09121111111"
        assert refreshed.birth_date == "1375/07/22"


def test_ui_fixes_markup_and_js_contracts():
    """Verify modal layouts, removed cancel/refresh buttons, expiring contrast, icon bg removal, and redesigned devices."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    admin_users_js = Path("bot/web/static/js/admin_users.js").read_text(encoding="utf-8")
    profile_py = Path("bot/handlers/profile.py").read_text(encoding="utf-8")

    # 1. Kill All & Kill Single Device modals: header flex close button & no Cancel button
    for modal_id, next_marker in (
        ("killAllSessionsModal", 'id="killSingleDeviceModal"'),
        ("killSingleDeviceModal", 'id="giftModal"'),
    ):
        start = app_html.find(f'id="{modal_id}"')
        end = app_html.find(next_marker, start + 1)
        assert start != -1 and end != -1
        block = app_html[start:end]
        assert "modal-close-btn shrink-0" in block
        assert "modal-close-btn absolute top-3 left-3" not in block
        assert "انصراف" not in block

    # 2. Modify user modal (افزایش حجم و تمدید اشتراک): no Cancel button
    mod_start = admin_html.find('id="modifyUserModal"')
    mod_end = admin_html.find('id="walletModal"', mod_start)
    mod_block = admin_html[mod_start:mod_end]
    assert "انصراف" not in mod_block

    # 3. HWID modal: no refresh icon button in header
    hwid_start = admin_html.find('id="hwidModal"')
    hwid_end = admin_html.find('id="bulkUsersModal"', hwid_start)
    hwid_block = admin_html[hwid_start:hwid_end]
    assert "refreshCurrentDeviceTab" not in hwid_block

    # 4. Admin users expiring badge has strong light-mode contrast
    assert "text-amber-800 dark:text-amber-300 border border-amber-600/50" in admin_users_js

    # 5. Admin devices tab redesigned like user's active sessions
    assert "window.parseDeviceMeta" in admin_users_js
    assert "کلاینت:" in admin_users_js
    assert "زمان ثبت:" in admin_users_js
    assert "آخرین فعالیت:" in admin_users_js

    # 6. User profile modal has birthday-only admin edit UI with icon-only toggle, and bot profile menu hides Edit Birthday when set
    assert 'id="userProfModalEditToggleBtn"' in admin_html
    assert 'id="userProfEditBirthday"' in admin_html
    assert 'id="userProfEditPhone"' not in admin_html
    assert 'id="userProfEditFullName"' not in admin_html
    assert "<span>ویرایش</span>" not in admin_html[admin_html.find('id="userProfileModal"'):admin_html.find('id="modifyUserModal"')]
    assert "saveUserProfileEdit" in admin_users_js
    assert "ویرایش تاریخ تولد" not in profile_py

    # 7. Recommended & alternative app icons in app.js are gold/silver medals with no tinted circular background
    assert 'bg-amber-500/25' not in app_js
    assert 'bg-sky-500/20' not in app_js
    assert 'title="پیشنهادی">🥇</span>' in app_js
    assert 'title="جایگزین">🥈</span>' in app_js

    # 8. Admin devices modal: overflow guards, no IP copy icon in devices tab, create user squad mandatory & HWID placeholder
    assert "btn-copy-hwid-ip" in admin_users_js
    assert 'data-ip="${escapeHtml(ip)}" title="کلیک جهت کپی آی‌پی">${escapeHtml(ip)}</button>' in admin_users_js
    assert 'placeholder="خالی = پیش‌فرض پنل"' in admin_html
    assert "انتخاب اسکواد داخلی الزامی است" in admin_users_js
    create_start = admin_html.find('id="createUserModal"')
    create_end = admin_html.find('id="planPickerModal"', create_start)
    create_block = admin_html[create_start:create_end]
    assert "s-danger-soft border" in create_block
    assert "اختیاری" not in create_block[create_block.find("اسکواد داخلی"):]

    # 9. Admin node billing strip & Iran flag badge & Admin apps tutorial cleanup
    admin_nodes_js = Path("bot/web/static/js/admin_nodes.js").read_text(encoding="utf-8")
    admin_plans_js = Path("bot/web/static/js/admin_plans.js").read_text(encoding="utf-8")
    admin_settings_js = Path("bot/web/static/js/admin_settings.js").read_text(encoding="utf-8")
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    components_css = Path("bot/web/static/css/components.css").read_text(encoding="utf-8")

    assert "قیمت تمام‌شده به ازای هر گیگ:" in admin_nodes_js
    assert "قیمت تمام‌شده هر گیگ:" not in admin_nodes_js
    assert "roi_percent" not in admin_nodes_js
    assert "iran" in admin_plans_js and "سرور ایران" in admin_plans_js
    assert "badge-iran" in shop_js and "btn-plan-iran" in shop_js
    assert ".shop-plan-badge.badge-iran" in components_css and ".btn-plan-iran" in components_css
    assert "appTutorial_" not in admin_html
    assert "appTutorial_" not in admin_settings_js
    assert "لینک دانلود نسخه اصلی / نصبی (Setup):" not in admin_html
    assert "لینک دانلود نسخه نصبی (Setup):" in admin_html
    assert 'data-store-only="1"' in admin_html
    assert "storeOnly" in admin_settings_js
    assert "DL_ICON_PLAYSTORE" in app_js and "DL_ICON_APPSTORE" in app_js and "DL_ICON_DIRECT" in app_js

    # 10. Banned lock screen, app label cleanup, v2raytun, SRH stacked LTR layout & node FX subrow
    assert 'id="systemBannedScreen"' in app_html
    assert "applySystemBlockScreen('banned'" in app_js
    assert "لینک دانلود نرم‌افزار (اپ‌استور):" not in admin_html
    assert "لینک دانلود نرم‌افزار (گوگل‌پلی):" not in admin_html
    assert "لینک دانلود گیت‌هاب / مستقیم" not in admin_html
    assert "لینک دانلود مستقیم:" in admin_html
    assert "appDownloadExtra_macos_hiddify" in admin_html
    assert "id: 'v2raytun'" in app_js
    assert "v2raytun:" in admin_settings_js
    assert "ارائه‌دهنده (هاست)" not in admin_nodes_js
    assert "هزینه ارزی سرویس:" in admin_nodes_js
    assert "px-2.5 text-xs" in admin_html[admin_html.find('id="hwidModal"'):admin_html.find('id="bulkUsersModal"')]
    assert "'موفق'" not in admin_users_js[admin_users_js.find("async loadUserSrh"):admin_users_js.find("async loadHwidDevices")]

    # 11. v2RayTun real PNG/WebP icon, node cost rows (Toman + Dollar + Euro, no due border/icon, inline provider/cost),
    #     user profile no Back button, plans header swap, planModal scroll padding, coupon Toman below price & "+ کارت شارژ"
    assert Path("bot/web/static/img/apps/v2raytun.png").is_file()
    assert Path("bot/web/static/img/apps/v2raytun.webp").is_file()
    assert "هزینه یورویی سرور:" in admin_nodes_js
    assert "🗓️" not in admin_nodes_js
    assert 'روز مانده</span>' in admin_nodes_js
    prof_start = admin_html.find('id="userProfModalEditBody"')
    prof_end = admin_html.find('id="modifyUserModal"', prof_start)
    assert "بازگشت" not in admin_html[prof_start:prof_end]
    plan_modal_start = admin_html.find('id="planModal"')
    plan_modal_end = admin_html.find('id="couponModal"', plan_modal_start)
    assert "py-2 px-2.5" in admin_html[plan_modal_start:plan_modal_end]
    assert "تولید کارت شارژ" not in admin_html[admin_html.find('id="subtabContentCoupons"'):admin_html.find('id="tab-admin-nodes"')]
    assert "<span>+</span> کارت شارژ" in admin_html
    assert "Top Row: Price and تومان on Right, Icons + Name + statusBadge flush Left" in admin_plans_js
    assert "flex-col items-center justify-center flex-shrink-0 text-center leading-tight min-w-[45px]" in admin_plans_js


@pytest.mark.anyio
async def test_srh_incy_no_duplicate_os_and_v2raytun_detection():
    """Verify _parse_client_app avoids duplicate OS label on Incy and recognizes v2RayTun."""
    from bot.web.admin_users_detail import _parse_client_app

    incy_win = _parse_client_app("Incy/1.0.8 Windows")
    assert incy_win["name"] == "Incy"
    assert incy_win["tag"] == "ویندوز"

    tun_ios = _parse_client_app("v2RayTun/2.4.0 CFNetwork iOS")
    assert tun_ios["name"] == "v2RayTun"
    assert tun_ios["tag"] == "iOS"


@pytest.mark.anyio
async def test_payment_methods_chart_includes_all_gateways(session_factory):
    """Verify payment distribution includes manual card, auto card, TON, TRX, POL, and Stars."""
    from datetime import datetime, timezone
    from bot.db.models import CardAutoInvoice, CryptoInvoice, Topup, TopupStatus
    from bot.web.admin_overview_charts import _calc_retention_and_payments

    async with session_factory() as session:
        session.add(Topup(telegram_id=101, amount=100_000, status=TopupStatus.APPROVED.value, receipt_hash="photo:abc"))
        session.add(Topup(telegram_id=102, amount=50_000, status=TopupStatus.APPROVED.value, receipt_hash="stars:xyz"))
        session.add(CardAutoInvoice(
            invoice_uuid="ca-1",
            telegram_id=103,
            base_amount=200_000,
            exact_amount=200_123,
            exact_rial=2_001_230,
            card_number="6037",
            card_holder="Test",
            status="paid",
            expires_at=datetime.now(timezone.utc),
        ))
        session.add(CryptoInvoice(
            telegram_id=104, amount_toman=300_000, amount_ton="1.5", nanotons=1500, currency="ton", comment="t1", pay_address="a1", status="paid", expires_at=datetime.now(timezone.utc)
        ))
        session.add(CryptoInvoice(
            telegram_id=105, amount_toman=400_000, amount_ton="10", nanotons=1000, currency="TRX", comment="t2", pay_address="a2", status="paid", expires_at=datetime.now(timezone.utc)
        ))
        session.add(CryptoInvoice(
            telegram_id=106, amount_toman=500_000, amount_ton="20", nanotons=2000, currency="POL", comment="t3", pay_address="a3", status="paid", expires_at=datetime.now(timezone.utc)
        ))
        await session.commit()

        p_dist, _ = await _calc_retention_and_payments(session, datetime.now(timezone.utc))
        stats = dict(zip(p_dist["labels"], zip(p_dist["counts"], p_dist["volumes"])))
        assert stats["کارت به کارت (دستی)"] == (1, 100_000)
        assert stats["کارت به کارت (خودکار)"] == (1, 200_000)
        assert stats["تون‌کوین (TON)"] == (1, 300_000)
        assert stats["ترون (TRX)"] == (1, 400_000)
        assert stats["پلیگان (POL)"] == (1, 500_000)
        assert stats["تلگرام استارز (XTR)"] == (1, 50_000)

    # Guard against PostgreSQL GroupingError: must group directly on CryptoInvoice.currency column
    charts_src = Path("bot/web/admin_overview_charts.py").read_text(encoding="utf-8")
    assert ".group_by(CryptoInvoice.currency)" in charts_src

    # 12. Iran badge border removal & margin separation, colored OS icons, larger medals, 6h manual-card lock UI
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    components_css = Path("bot/web/static/css/components.css").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")

    iran_badge_css = components_css[components_css.find(".shop-plan-badge.badge-iran"):components_css.find(".btn-plan-iran") + 260]
    assert "border-bottom: 2px solid #ffffff" not in iran_badge_css
    assert "rgba(255, 255, 255, 0.65)" not in iran_badge_css
    assert "flex items-center justify-between gap-2" in shop_js
    assert 'text-2xl leading-none bg-transparent border-0 shadow-none flex-shrink-0" title="پیشنهادی">🥇' in app_js
    for color_hex in ("#22c55e", "#3ddc84", "#f25022", "#38bdf8", "#f59e0b"):
        assert color_hex in app_html
        assert color_hex in admin_html
    assert 'id="manualReceiptToggleWrapper"' in app_html
    assert 'id="manualReceiptLockBanner"' in app_html
    assert "applyManualCardLockState" in wallet_js
    assert "_cardTopupGuardState.manualBlockUntilMs" in wallet_js


@pytest.mark.anyio
async def test_manual_card_blocked_for_6h_after_card_auto_invoice(session_factory, tmp_path, monkeypatch):
    """Ensure pending/paid/expired CardAutoInvoice blocks manual card topup for 6h across WebApp and Bot."""
    import base64
    from contextlib import asynccontextmanager
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from bot.db.models import CardAutoInvoice
    from bot.db.repositories.card_auto_repo import CardAutoRepository
    from bot.handlers.wallet import c2c_manual_receipt_callback
    from bot.web.user_topup import get_user_topup_info, post_user_topup_card

    monkeypatch.chdir(tmp_path)
    tg_id = 555666777
    now = datetime.now(timezone.utc)
    store = SimpleNamespace(
        card_require_phone_verification=False,
        card_number="6219861912345678",
        card_holder="Test",
        card_enabled=True,
        card_auto_enabled=True,
        crypto_enabled=False,
        trx_enabled=False,
        pol_enabled=False,
        stars_enabled=False,
        topup_min_amount=10000,
        topup_max_amount=50000000,
    )

    async with session_factory() as session:
        @asynccontextmanager
        async def _fake_db_session(_req):
            yield session

        def _make_post_req(img_payload: bytes, amount: int = 50000):
            b64 = "data:image/jpeg;base64," + base64.b64encode(img_payload).decode()
            body = {"amount": amount, "receipt_text": "", "receipt_image": b64}
            req = make_mocked_request("POST", "/api/user/topup/card")
            fake_app = {"cache": None, "bot": None, "settings": SimpleNamespace(ADMIN_CHAT_ID=0)}
            return SimpleNamespace(app=fake_app, headers=req.headers, query={}, json=AsyncMock(return_value=body))

        # 1. Pending auto-invoice locks manual entry & upload
        pending_inv = CardAutoInvoice(
            invoice_uuid="c2c_lock_pending",
            telegram_id=tg_id,
            base_amount=50000,
            exact_amount=50321,
            exact_rial=503210,
            card_number="6219861912345678",
            card_holder="Test",
            status="pending",
            expires_at=now + timedelta(minutes=55),
            created_at=now,
        )
        session.add(pending_inv)
        await session.commit()

        info_req = SimpleNamespace(app={"cache": None}, query={}, headers={})
        with patch("bot.web.user_topup.require_user", return_value=({"id": tg_id, "is_preview": False, "first_name": "T"}, None)), \
             patch("bot.web.user_topup.enforce_invite_only", AsyncMock(return_value=None)), \
             patch("bot.web.user_topup.db_session", side_effect=_fake_db_session), \
             patch("bot.web.user_topup.get_store_settings", AsyncMock(return_value=store)):
            info_resp = await get_user_topup_info(info_req)
            info_data = json.loads(info_resp.text)
            assert info_data["manual_card_blocked"] is True
            assert info_data["manual_card_block_remaining_seconds"] > 18000

            post_resp = await post_user_topup_card(_make_post_req(b"receipt-pending" * 8, amount=50000))
            assert post_resp.status == 400
            post_data = json.loads(post_resp.text)
            assert post_data["error"] == "manual_card_cooldown"

        # Bot callback c2c_manual_receipt_callback must also refuse while locked
        call = MagicMock()
        call.from_user = SimpleNamespace(id=tg_id, username="tester")
        call.data = f"wallet:manual_receipt:{pending_inv.invoice_uuid}"
        call.answer = AsyncMock()
        mock_user_repo = MagicMock()
        mock_user_repo.get_or_create = AsyncMock(return_value=SimpleNamespace(telegram_id=tg_id, language="fa"))
        mock_state = MagicMock()
        mock_state.set_state = AsyncMock()
        await c2c_manual_receipt_callback(call, MagicMock(), mock_user_repo, session, mock_state)
        call.answer.assert_awaited_once()
        assert call.answer.call_args.kwargs.get("show_alert") is True
        mock_state.set_state.assert_not_awaited()

        # 2. Paid auto-invoice STILL locks manual upload even when submitted amount differs from exact_amount
        pending_inv.status = "paid"
        pending_inv.paid_at = now - timedelta(hours=2)
        await session.commit()

        with patch("bot.web.user_topup.require_user", return_value=({"id": tg_id, "is_preview": False, "first_name": "T"}, None)), \
             patch("bot.web.user_topup.enforce_invite_only", AsyncMock(return_value=None)), \
             patch("bot.web.user_topup.db_session", side_effect=_fake_db_session), \
             patch("bot.web.user_topup.get_store_settings", AsyncMock(return_value=store)):
            post_paid_resp = await post_user_topup_card(_make_post_req(b"receipt-paid-diff" * 8, amount=50000))
            assert post_paid_resp.status == 400
            assert json.loads(post_paid_resp.text)["error"] == "manual_card_cooldown"

        # 3. Past 6 hours unlocks cleanly
        pending_inv.paid_at = now - timedelta(hours=6, minutes=1)
        pending_inv.created_at = now - timedelta(hours=6, minutes=1)
        await session.commit()

        block = await CardAutoRepository(session).get_manual_card_block_info(tg_id)
        assert block is None

        with patch("bot.web.user_topup.require_user", return_value=({"id": tg_id, "is_preview": False, "first_name": "T"}, None)), \
             patch("bot.web.user_topup.enforce_invite_only", AsyncMock(return_value=None)), \
             patch("bot.web.user_topup.db_session", side_effect=_fake_db_session), \
             patch("bot.web.user_topup.get_store_settings", AsyncMock(return_value=store)):
            post_ok_resp = await post_user_topup_card(_make_post_req(b"receipt-after-6h" * 8, amount=50000))
            assert post_ok_resp.status == 200


@pytest.mark.anyio
async def test_node_billing_inline_rows_due_date_ui_plan_align_and_due_alert(session_factory):
    """Verify inline node revenue/profit rows, per-GB label, polished date input & fonts, left-aligned plan icons, and immediate/retryable 3-day node alerts."""
    from datetime import datetime, timedelta, timezone
    from aiohttp.test_utils import make_mocked_request
    from bot.db.repositories.node_cost_repo import NodeCostRepository
    from bot.services.node_monitor import check_nodes_billing_due_dates
    from bot.web.admin_infra_api import post_admin_node_cost
    from bot.web.cache import FastCache

    admin_nodes_js = Path("bot/web/static/js/admin_nodes.js").read_text(encoding="utf-8")
    admin_plans_js = Path("bot/web/static/js/admin_plans.js").read_text(encoding="utf-8")
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    components_css = Path("bot/web/static/css/components.css").read_text(encoding="utf-8")
    charts_js = Path("bot/web/static/js/charts.js").read_text(encoding="utf-8")

    # 1. Node inline revenue/net profit rows & per-GB label
    rev_idx = admin_nodes_js.find("درآمد تخمینی نود:")
    prof_idx = admin_nodes_js.find("سود/زیان خالص:")
    assert 'flex items-center justify-between gap-2' in admin_nodes_js[rev_idx - 60:prof_idx]
    assert 'flex items-center justify-between gap-2' in admin_nodes_js[prof_idx - 120:prof_idx + 20]
    assert "قیمت تمام‌شده به ازای هر گیگ:" in admin_nodes_js

    # 2. Node billing modal: split notes (اختیاری), polished Vazirmatn date input & no font-mono
    billing_modal = admin_html[admin_html.find('id="nodeBillingModal"'):admin_html.find('id="campaignDetailModal"')]
    assert "node-date-input" in billing_modal
    assert "[color-scheme:dark]" not in billing_modal
    assert "addDaysToNodeBillingDueDate(30)" in billing_modal
    assert ">یادداشت و مشخصات:</label>" in billing_modal
    assert ">(اختیاری)</span>" in billing_modal
    assert 'input[type="date"]' in components_css
    assert "::-webkit-datetime-edit" in components_css
    assert "font-mono" not in charts_js

    # 3. Admin plan card: flush left with icons before English name
    plan_top = admin_plans_js[admin_plans_js.find("Top Row:"):admin_plans_js.find("Bottom Row:")]
    assert "flex items-center justify-start gap-1.5 min-w-0 flex-1" in plan_top
    assert plan_top.find("${pkgIcon}") < plan_top.find("${escapeHtml(cleanName)}")

    # 4. Failed Telegram delivery must NOT mark alert_notified=True, and saving <=3d due_date fires alert immediately
    now_utc = datetime.now(timezone.utc)
    async with session_factory() as session:
        repo = NodeCostRepository(session)
        await repo.upsert(
            node_uuid="nl-node-1",
            node_name="Netherlands",
            provider="Worldstream",
            monthly_cost_toman=1200000,
            due_date=now_utc + timedelta(days=3),
        )
        await session.commit()

    failing_bot = MagicMock()
    failing_bot.send_message = AsyncMock(side_effect=RuntimeError("Telegram temporary timeout"))
    with patch("bot.services.node_monitor.get_settings") as mock_cfg:
        mock_cfg.return_value.ADMIN_CHAT_ID = 0
        mock_cfg.return_value.ADMIN_IDS = [777001]
        mock_cfg.return_value.TIMEZONE = "Asia/Tehran"
        await check_nodes_billing_due_dates(failing_bot, session_factory)

    async with session_factory() as session:
        item = await NodeCostRepository(session).get_by_uuid("nl-node-1")
        assert item is not None and item.alert_notified is False

    ok_bot = MagicMock()
    ok_bot.send_message = AsyncMock()
    req_post = make_mocked_request(
        "POST",
        "/api/admin/infra/node-cost",
        headers={"content-type": "application/json"},
        app={
            "session_factory": session_factory,
            "cache": FastCache(),
            "bot": ok_bot,
        },
    )
    req_post.json = AsyncMock(return_value={
        "node_uuid": "nl-node-1",
        "node_name": "Netherlands",
        "provider": "Worldstream",
        "monthly_cost_toman": 1200000,
        "monthly_cost_eur": 10.0,
        "currency": "EUR",
        "due_date": (now_utc + timedelta(days=2)).strftime("%Y-%m-%d"),
    })
    with patch("bot.web.admin_infra_api._check_admin", return_value={"id": 12345, "is_admin": True}), \
         patch("bot.services.node_monitor.get_settings") as mock_cfg:
        mock_cfg.return_value.ADMIN_CHAT_ID = 0
        mock_cfg.return_value.ADMIN_IDS = [777001]
        mock_cfg.return_value.TIMEZONE = "Asia/Tehran"
        resp = await post_admin_node_cost(req_post)
        assert resp.status == 200
        assert ok_bot.send_message.called
        assert "Netherlands" in ok_bot.send_message.call_args[0][1]

    async with session_factory() as session:
        item_after = await NodeCostRepository(session).get_by_uuid("nl-node-1")
        assert item_after is not None and item_after.alert_notified is True


def test_shop_card_header_invoice_buyer_modals_and_banned_scroll_fixes():
    """Verify shop card alignment, invoice buyer alignment, light-mode report label, access mode dropdown, create/modify placeholders, bulk status picker modal, and banned scroll/CTA."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    admin_users_js = Path("bot/web/static/js/admin_users.js").read_text(encoding="utf-8")
    admin_settings_js = Path("bot/web/static/js/admin_settings.js").read_text(encoding="utf-8")
    components_css = Path("bot/web/static/css/components.css").read_text(encoding="utf-8")

    # 1. Shop card: corner badge top-left, Price top-right, Title & discount/coupon badges left-aligned below corner badge
    assert "rounded-br-xl" in shop_js
    assert 'min-w-0 flex-1 ${planBadge ? \'mt-4\' : \'\'}" dir="ltr"' in shop_js
    assert 'flex items-center justify-start gap-1.5 mt-1.5 flex-wrap' in shop_js
    assert "border-bottom: 1.5px solid" in components_css[components_css.find("/* --- 16. Shop Plan Badges --- */"):]

    # 2. Invoice modal Buyer content full-width left-aligned in both HTML and JS (no inline-block .num-bidi override)
    buyer_idx = app_html.find("👤 خریدار:")
    buyer_block = app_html[buyer_idx:buyer_idx + 350]
    assert 'class="w-full text-left font-sans" dir="ltr"' in buyer_block
    assert 'id="invBuyerName" class="font-bold t-main block w-full truncate text-xs select-all text-left"' in buyer_block
    assert 'id="invBuyerId" class="text-[11px] text-slate-400 font-sans block w-full select-all text-left"' in buyer_block
    assert "text-[11px] text-slate-400 font-sans block w-full select-all text-left" in app_js

    # 3. Broadcast report modal light-mode contrast
    report_block = admin_html[admin_html.find('id="broadcastReportModal"'):admin_html.find('id="dismissReportModalBtn"')]
    assert 'id="reportTargetLabel" class="text-cyan-700 dark:text-cyan-300 font-extrabold text-[11px]"' in report_block

    # 4. Access mode button matches Timezone selector styling
    assert 'id="openAccessModeModalBtn"' in admin_html
    access_btn_block = admin_html[admin_html.find('id="openAccessModeModalBtn"'):admin_html.find('id="openTimezoneModalBtn"')]
    assert 'id="accessModeBadge"' in access_btn_block
    assert "▾" in access_btn_block
    assert "t-success font-bold text-[11px] whitespace-nowrap" in admin_settings_js

    # 5. Create user modal cleanup (no asterisk before الزامی, select placeholder, input placeholders, bordered اختیاری, planPickerList scroll gap)
    create_block = admin_html[admin_html.find('id="createUserModal"'):admin_html.find('id="planPickerModal"')]
    assert "* الزامی" not in create_block
    assert '>الزامی</span>' in create_block
    assert 's-neutral-soft border text-[10.5px] font-bold px-2 py-0.5 rounded-lg font-sans">اختیاری</span>' in create_block
    assert 'placeholder="پیش\u200cفرض: خودکار"' in create_block
    assert 'id="createUserPlanLabel" class="text-xs text-white font-medium truncate">انتخاب کنید<' in create_block
    assert 'placeholder="0 = نامحدود"' in create_block
    assert 'placeholder="مثلاً 30"' in create_block
    assert 'id="planPickerList" class="space-y-2 flex-1 overflow-y-auto custom-scroll max-h-[55vh] text-xs px-2.5 py-1.5"' in admin_html
    assert "if (labelEl) labelEl.innerText = 'انتخاب کنید';" in admin_users_js

    # 5b. High-risk users modal device count renders in explicit RTL order (5 دستگاه, not دستگاه 5)
    admin_charts_js = Path("bot/web/static/js/admin_charts.js").read_text(encoding="utf-8")
    assert '<span>🔥</span><bdi dir="ltr" class="num-bidi font-bold">${devCount}</bdi><span>دستگاه</span>' in admin_charts_js

    # 6. Bulk users modal uses dedicated custom status picker modal instead of raw select
    bulk_block = admin_html[admin_html.find('id="bulkUsersModal"'):admin_html.find('id="bulkStatusPickerModal"')]
    assert '<select id="bulkStatusSelect"' not in bulk_block
    assert 'type="hidden" id="bulkStatusSelect"' in bulk_block
    assert "openBulkStatusPickerModal" in admin_html and "openBulkStatusPickerModal" in admin_users_js
    assert 'id="bulkStatusPickerModal"' in admin_html

    # 7. Modify user modal placeholders & labels
    mod_block = admin_html[admin_html.find('id="modifyUserModal"'):admin_html.find('id="walletModal"')]
    assert "اختیاری (0 = بدون تغییر)" not in mod_block
    assert mod_block.count('placeholder="0 = بدون تغییر"') == 2

    # 8. Banned screen dark-mode CTA polish & scroll lock
    assert "linear-gradient(135deg, #e11d48 0%, #be123c 100%)" in components_css
    assert "contentArea.classList.toggle('system-blocked-active', isBlocked)" in app_js
    assert "contentArea.classList.toggle('overflow-hidden', isBlocked)" in app_js
