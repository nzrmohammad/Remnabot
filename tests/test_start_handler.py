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
