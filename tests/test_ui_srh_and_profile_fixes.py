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

    # 6. User profile modal has admin edit UI, and bot profile menu hides Edit Birthday when set
    assert 'id="userProfModalEditToggleBtn"' in admin_html
    assert 'id="userProfEditBirthday"' in admin_html
    assert 'id="userProfEditPhone"' in admin_html
    assert 'id="userProfEditFullName"' in admin_html
    assert "saveUserProfileEdit" in admin_users_js
    assert "ویرایش تاریخ تولد" not in profile_py

    # 7. Recommended & alternative app icons in app.js have no tinted circular background
    assert 'bg-amber-500/25' not in app_js
    assert 'bg-sky-500/20' not in app_js
    assert 'title="پیشنهادی">⭐️</span>' in app_js
    assert 'title="جایگزین">🔄</span>' in app_js
