import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from bot.db.models import Service, User, Wallet
from bot.services.purchases import execute_purchase, resolve_squad_name
from bot.services.render import render_services
from bot.web.admin_plans import post_admin_plan_save


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_squad_switch_in_purchases(session_factory):
    """Test that switching a full plan to another squad updates panel squad, resets consumed traffic, and sets squad_changed flag."""
    tid = 998877
    async with session_factory() as session:
        user = User(telegram_id=tid, username="switch_user", full_name="Switch User")
        wallet = Wallet(telegram_id=tid, balance=200000)
        svc_tunnel = Service(
            id=101,
            name="Tunnel VIP",
            price=120000,
            duration_days=30,
            traffic_gb=50,
            traffic_strategy="NO_RESET",
            squad_uuid="sq-tunnel-uuid",
            is_active=True,
            hwid_limit=3,
        )
        session.add_all([user, wallet, svc_tunnel])
        await session.commit()

    remnawave = MagicMock()
    existing_account = {
        "id": 45,
        "username": "switch_user_panel",
        "status": "ACTIVE",
        "expireAt": "2026-12-01T00:00:00Z",
        "trafficLimitBytes": 20 * 1024**3,
        "activeInternalSquads": ["sq-normal-uuid"],
        "subscriptionUrl": "https://sub.domain/sub/45",
    }
    remnawave.get_users_by_telegram_id = AsyncMock(return_value=[existing_account])
    remnawave.set_user_squads = AsyncMock(return_value={"id": 45})
    remnawave.update_user_subscription = AsyncMock(return_value={"id": 45, "subscriptionUrl": "https://sub.domain/sub/45"})
    remnawave.reset_user_traffic = AsyncMock(return_value=True)
    remnawave.update_user_fields = AsyncMock(return_value=True)

    with patch("bot.services.app_settings.is_maintenance", AsyncMock(return_value=False)), \
         patch("bot.services.purchases.get_store_settings", AsyncMock(return_value=MagicMock(default_squad_uuid=None))):

        async with session_factory() as session:
            svc = await session.get(Service, 101)
            res = await execute_purchase(
                remnawave=remnawave,
                session=session,
                service=svc,
                telegram_id=tid,
                chosen_account=existing_account,
            )

            assert res.ok is True
            assert res.kind == "success"
            assert res.squad_changed is True

            # Verify set_user_squads was called with target squad
            remnawave.set_user_squads.assert_awaited_once_with(45, ["sq-tunnel-uuid"])

            # Verify reset_user_traffic was called
            remnawave.reset_user_traffic.assert_awaited_once_with(45)

            # Verify hwid limit was updated
            remnawave.update_user_fields.assert_awaited_once_with(45, hwidDeviceLimit=3)


@pytest.mark.anyio
async def test_admin_plan_mandatory_squad(session_factory):
    """Test that creating or updating a plan without squad_uuid returns HTTP 400 error."""
    # 1. Missing squad_uuid
    req_invalid = MagicMock()
    req_invalid.app = {"session_factory": session_factory}
    req_invalid.headers = {"X-Admin-Key": "test"}
    req_invalid.json = AsyncMock(return_value={
        "name": "No Squad Plan",
        "price": 50000,
        "traffic_gb": 30,
        "duration_days": 30,
        "squad_uuid": "",
    })

    with patch("bot.web.admin_plans._check_admin", return_value={"id": 1, "username": "admin"}):
        resp = await post_admin_plan_save(req_invalid)
        assert resp.status == 400
        data = json.loads(resp.text)
        assert data["ok"] is False
        assert "اسکواد" in data["error"]

    # 2. Valid squad_uuid
    req_valid = MagicMock()
    req_valid.app = {"session_factory": session_factory}
    req_valid.headers = {"X-Admin-Key": "test"}
    req_valid.json = AsyncMock(return_value={
        "name": "Squad Plan",
        "price": 50000,
        "traffic_gb": 30,
        "duration_days": 30,
        "squad_uuid": "sq-valid-123",
    })

    with patch("bot.web.admin_plans._check_admin", return_value={"id": 1, "username": "admin"}):
        resp_valid = await post_admin_plan_save(req_valid)
        assert resp_valid.status == 200
        data_valid = json.loads(resp_valid.text)
        assert data_valid["ok"] is True


@pytest.mark.anyio
async def test_catalog_filtering_by_squad(session_factory):
    """Test squad-aware catalog filtering: add-ons only shown when matching active account squad."""
    tid = 554433
    async with session_factory() as session:
        user = User(telegram_id=tid, username="cat_user", full_name="Cat User")
        wallet = Wallet(telegram_id=tid, balance=100000)
        s1 = Service(id=201, name="Normal Base Plan", price=50000, duration_days=30, traffic_gb=50, squad_uuid="sq-normal", is_active=True)
        s2 = Service(id=202, name="Tunnel Base Plan", price=80000, duration_days=30, traffic_gb=50, squad_uuid="sq-tunnel", is_active=True)
        s3 = Service(id=203, name="Normal Extra Traffic", price=20000, duration_days=0, traffic_gb=10, badge="traffic", squad_uuid="sq-normal", is_active=True)
        s4 = Service(id=204, name="Tunnel Extra Traffic", price=35000, duration_days=0, traffic_gb=10, badge="traffic", squad_uuid="sq-tunnel", is_active=True)
        session.add_all([user, wallet, s1, s2, s3, s4])
        await session.commit()

    bot = MagicMock()
    user_repo = MagicMock()
    mock_rendered_text = []

    async def mock_render_menu(_bot, _user, _repo, text, _kb):
        mock_rendered_text.append(text)

    # Case A: User has NO active accounts -> should see base plans (s1, s2) and NO addons (s3, s4)
    remnawave_no_acc = MagicMock()
    remnawave_no_acc.get_users_by_telegram_id = AsyncMock(return_value=[])

    with patch("bot.services.render.render_menu", mock_render_menu):
        async with session_factory() as session:
            await render_services(bot, user, user_repo, session, remnawave=remnawave_no_acc)
            assert len(mock_rendered_text) == 1
            rendered = mock_rendered_text[0]
            assert "Normal Base Plan" in rendered
            assert "Tunnel Base Plan" in rendered
            assert "Normal Extra Traffic" not in rendered
            assert "Tunnel Extra Traffic" not in rendered

    # Case B: User has active account in Normal squad -> should see s1, s2 and Normal addon (s3), but NOT Tunnel addon (s4)
    mock_rendered_text.clear()
    remnawave_normal = MagicMock()
    normal_acc = {
        "id": 88,
        "username": "user_norm",
        "status": "ACTIVE",
        "activeInternalSquads": ["sq-normal"],
    }
    remnawave_normal.get_users_by_telegram_id = AsyncMock(return_value=[normal_acc])

    with patch("bot.services.render.render_menu", mock_render_menu):
        async with session_factory() as session:
            await render_services(bot, user, user_repo, session, remnawave=remnawave_normal)
            assert len(mock_rendered_text) == 1
            rendered = mock_rendered_text[0]
            assert "Normal Base Plan" in rendered
            assert "Tunnel Base Plan" in rendered
            assert "Normal Extra Traffic" in rendered
            assert "Tunnel Extra Traffic" not in rendered


@pytest.mark.anyio
async def test_resolve_squad_name():
    """Test human-readable squad name lookup helper."""
    remnawave = MagicMock()
    remnawave.get_internal_squads = AsyncMock(return_value=[
        {"uuid": "sq-111", "name": "سرورهای ایران تانل"},
        {"uuid": "sq-222", "name": "سرورهای مستقیم آلمان"},
    ])

    name1 = await resolve_squad_name(remnawave, "sq-111")
    assert name1 == "سرورهای ایران تانل"

    name2 = await resolve_squad_name(remnawave, "sq-222")
    assert name2 == "سرورهای مستقیم آلمان"

    name_fallback = await resolve_squad_name(remnawave, "sq-unknown")
    assert name_fallback == "sq-unknown"


@pytest.mark.anyio
async def test_squad_switch_warning_screen_before_invoice(session_factory):
    """Test that selecting a service with a different squad renders the warning screen first, and confirming renders invoice."""
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.types import CallbackQuery, User as TgUser
    from bot.db.repositories.user_repo import UserRepository
    from bot.handlers.shop_renew import buy_for_account

    tid = 112233
    async with session_factory() as session:
        user = User(telegram_id=tid, username="switch_user2", full_name="Switch User 2", language="fa", is_verified=True)
        wallet = Wallet(telegram_id=tid, balance=200000)
        svc_tunnel = Service(
            id=202,
            name="Tunnel VIP 2",
            price=150000,
            duration_days=30,
            traffic_gb=60,
            traffic_strategy="NO_RESET",
            squad_uuid="sq-tunnel-2",
            is_active=True,
        )
        session.add_all([user, wallet, svc_tunnel])
        await session.commit()

    remnawave = MagicMock()
    existing_acc = {
        "id": 99,
        "username": "switch_user2_panel",
        "status": "ACTIVE",
        "activeInternalSquads": ["sq-normal-2"],
    }
    remnawave.get_users_by_telegram_id = AsyncMock(return_value=[existing_acc])
    remnawave.get_internal_squads = AsyncMock(return_value=[
        {"uuid": "sq-normal-2", "name": "نرمال"},
        {"uuid": "sq-tunnel-2", "name": "تانل اختصاصی"},
    ])

    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.edit_message_text = AsyncMock()
    rendered_menus = []

    async def mock_render_menu(b, u, ur, text, kb=None):
        rendered_menus.append((text, kb))

    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=tid, user_id=tid)
    state = FSMContext(storage=storage, key=key)

    call = MagicMock(spec=CallbackQuery)
    call.from_user = TgUser(id=tid, is_bot=False, first_name="Switch", username="switch_user2")
    call.data = "svc:buya:202:99"
    call.answer = AsyncMock()

    with patch("bot.handlers.shop_renew.render_menu", mock_render_menu), \
         patch("bot.handlers.shop_purchase_views.render_menu", mock_render_menu), \
         patch("bot.services.app_settings.is_maintenance", AsyncMock(return_value=False)):
        async with session_factory() as session:
            user_repo = UserRepository(session)
            # Step 1: Initial click -> warning screen must be shown
            await buy_for_account(call, bot, user_repo, session, remnawave, state, service_id=202, panel_user_id="99")
            assert len(rendered_menus) == 1
            text, kb = rendered_menus[0]
            assert "هشدار مهم تغییر دسته سرور" in text
            assert "تانل اختصاصی" in text
            assert "حجم و روزهای باقیمانده بسته قبلی شما جایگزین می‌شوند" in text
            assert "لینک اتصال اشتراک شما تغییری نمی‌کند" in text
            assert "Update Subscription" in text

            # Check that the confirm button callback points to :ok
            all_buttons = [btn for row in kb.inline_keyboard for btn in row]
            ok_btn = next((b for b in all_buttons if b.callback_data == "svc:buya:202:99:ok"), None)
            assert ok_btn is not None
            assert "مشاهده پیش‌فاکتور" in ok_btn.text

            # Step 2: User confirms -> calls callback with :ok -> pre-invoice must be shown
            call.data = "svc:buya:202:99:ok"
            await buy_for_account(call, bot, user_repo, session, remnawave, state, service_id=202, panel_user_id="99")
            assert len(rendered_menus) == 2
            text2, kb2 = rendered_menus[1]
            assert "پیش‌فاکتور" in text2
            assert "ارتقای اشتراک به «تانل اختصاصی»" in text2
