from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo
import pytest

from bot.db.repositories.user_repo import UserRepository
from bot.handlers.inline import inline_query_handler
from bot.services.formatting import format_date, format_datetime


def test_format_datetime_tehran_tz_localization():
    # 2026-11-02 10:00:00 UTC is 13:30:00 in Asia/Tehran (UTC+3:30)
    utc_dt = datetime(2026, 11, 2, 10, 0, 0, tzinfo=timezone.utc)
    res_en = format_datetime(utc_dt, "en", tz_name="Asia/Tehran")
    assert "13:30" in res_en
    assert "2026-11-02" in res_en

    # Naive datetime is treated as UTC timestamp and converted to Tehran time
    naive_dt = datetime(2026, 11, 2, 21, 30, 0)
    # 21:30 UTC is 01:00 the NEXT day in Tehran!
    res_next_day = format_datetime(naive_dt, "en", tz_name="Asia/Tehran")
    assert "2026-11-03" in res_next_day
    assert "01:00" in res_next_day


def test_format_date_tehran_tz_localization():
    utc_dt = datetime(2026, 11, 2, 21, 30, 0, tzinfo=timezone.utc)
    res = format_date(utc_dt, "en", tz_name="Asia/Tehran")
    # Rolled over to Nov 3 in Tehran
    assert res == "2026-11-03"


@pytest.mark.anyio
async def test_inline_query_returns_rich_cards(session_factory):
    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create(telegram_id=777888, username="test_inline_user")

        query = MagicMock()
        query.from_user = MagicMock(id=777888)
        query.query = ""
        query.answer = AsyncMock()

        bot = AsyncMock()
        bot_user = MagicMock()
        bot_user.username = "MyTestVpnBot"
        bot.get_me.return_value = bot_user

        remnawave = AsyncMock()
        remnawave.get_users_by_telegram_id.return_value = [
            {
                "id": "101",
                "username": "samin",
                "trafficLimitBytes": 20 * (1024**3),
                "userTraffic": {"usedTrafficBytes": 5 * (1024**3)},
                "status": "ACTIVE",
                "subscriptionUrl": "https://sub.example.com/samin",
                "expireAt": "2026-12-01T00:00:00Z",
            }
        ]
        remnawave.get_nodes.return_value = [
            {"id": "n1", "name": "Frankfurt", "countryCode": "DE"},
            {"id": "n2", "name": "Helsinki", "countryCode": "FI"},
        ]

        await inline_query_handler(
            query=query,
            bot=bot,
            session=session,
            user_repo=user_repo,
            remnawave=remnawave,
        )

        assert query.answer.called
        call_kwargs = query.answer.call_args.kwargs
        results = call_kwargs.get("results")
        assert len(results) >= 3
        # First result should be the user's active sub
        sub_card = results[0]
        assert sub_card.id == "sub_101"
        assert "samin" in sub_card.title
        assert "15 GB" in sub_card.description

        # Second result should be referral
        ref_card = results[1]
        assert "ref_777888" in ref_card.id

        # Third result should be server status
        server_card = results[2]
        assert server_card.id == "server_status"
        assert "2 لوکیشن" in server_card.description


@pytest.mark.anyio
async def test_inline_query_keyword_filtering(session_factory):
    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create(telegram_id=999111, username="filter_user")

        query = MagicMock()
        query.from_user = MagicMock(id=999111)
        query.query = "ref"
        query.answer = AsyncMock()

        bot = AsyncMock()
        bot_user = MagicMock()
        bot_user.username = "MyTestVpnBot"
        bot.get_me.return_value = bot_user

        remnawave = AsyncMock()
        remnawave.get_users_by_telegram_id.return_value = []
        remnawave.get_nodes.return_value = []

        await inline_query_handler(
            query=query,
            bot=bot,
            session=session,
            user_repo=user_repo,
            remnawave=remnawave,
        )

        assert query.answer.called
        results = query.answer.call_args.kwargs.get("results")
        assert len(results) == 1
        assert "ref_999111" in results[0].id


@pytest.mark.anyio
async def test_inline_query_banned_user_empty(session_factory):
    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create(telegram_id=444555, username="banned_guy")
        user.is_banned = True
        await session.commit()

        query = MagicMock()
        query.from_user = MagicMock(id=444555)
        query.query = ""
        query.answer = AsyncMock()

        bot = AsyncMock()
        remnawave = AsyncMock()

        await inline_query_handler(
            query=query,
            bot=bot,
            session=session,
            user_repo=user_repo,
            remnawave=remnawave,
        )

        assert query.answer.called
        results = query.answer.call_args.kwargs.get("results")
        assert results == []
