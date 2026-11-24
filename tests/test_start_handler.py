import pytest
from unittest.mock import AsyncMock, MagicMock
from bot.handlers.start import cmd_start
from bot.db.repositories.user_repo import UserRepository


@pytest.mark.anyio
async def test_cmd_start_no_unbound_local_error(session_factory):
    async with session_factory() as session:
        user_repo = UserRepository(session)

        # Mock message
        message = MagicMock()
        message.from_user = MagicMock(id=987654321, username="testuser", full_name="Test User")
        message.text = "/start"
        message.answer = AsyncMock()

        # Mock Bot
        bot = AsyncMock()

        # Mock FSMContext
        state = AsyncMock()

        # Call cmd_start
        await cmd_start(
            message=message,
            bot=bot,
            user_repo=user_repo,
            session=session,
            state=state,
        )

        # Confirm answer was called (e.g. choose language or welcome)
        assert message.answer.called or bot.send_message.called


@pytest.mark.anyio
async def test_cmd_start_auto_verifies_existing_panel_user_and_hides_login_button(session_factory):
    """If Telegram ID exists in panel, /start silently verifies user and opens main menu directly;
    otherwise welcome keyboard offers only trial service (no login button)."""
    from types import SimpleNamespace
    from bot.db.models import AppSetting
    from bot.handlers.start import on_channel_member_updated
    from bot.keyboards.inline import welcome_keyboard

    # 1. welcome_keyboard has no auth:login button
    kb_unverified = welcome_keyboard("fa")
    cb_data = [btn.callback_data for row in kb_unverified.inline_keyboard for btn in row]
    assert "auth:login" not in cb_data
    assert "service:new" in cb_data

    async with session_factory() as session:
        user_repo = UserRepository(session)
        u = await user_repo.get_or_create(11223344, "auto_user", "Auto User")
        await user_repo.set_language(u, "fa")
        assert u.is_verified is False

        remnawave = AsyncMock()
        remnawave.telegram_id_exists = AsyncMock(return_value=True)

        msg = MagicMock()
        msg.from_user = MagicMock(id=11223344, username="auto_user", full_name="Auto User")
        msg.text = "/start"
        msg.answer = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        bot = AsyncMock()
        bot.send_message = AsyncMock(return_value=MagicMock(message_id=101))
        state = AsyncMock()

        await cmd_start(
            message=msg,
            bot=bot,
            user_repo=user_repo,
            session=session,
            state=state,
            remnawave=remnawave,
        )
        assert u.is_verified is True
        remnawave.telegram_id_exists.assert_awaited_once_with(11223344)

        # 2. Leaving join-gate channel triggers DM notification
        session.add(AppSetting(key="join_gate_enabled", value="1"))
        session.add(AppSetting(key="join_gate_channel", value="@RemnaTestChannel"))
        await session.flush()

        leave_event = SimpleNamespace(
            chat=SimpleNamespace(id=-100999888, username="RemnaTestChannel"),
            old_chat_member=SimpleNamespace(status="member"),
            new_chat_member=SimpleNamespace(
                status="left",
                user=SimpleNamespace(id=11223344, is_bot=False),
            ),
        )
        bot.send_message.reset_mock()
        await on_channel_member_updated(leave_event, bot=bot, user_repo=user_repo, session=session)
        bot.send_message.assert_awaited_once()
        sent_args = bot.send_message.call_args
        assert sent_args.args[0] == 11223344
        assert "خروج از کانال" in sent_args.args[1]

