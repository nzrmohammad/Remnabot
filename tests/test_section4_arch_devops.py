"""Regression tests for Section 4: Architecture, Scalability, Persistence, Migrations & DevOps."""
from __future__ import annotations

import asyncio
import base64
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image


@pytest.mark.anyio
async def test_live_sessions_explorer_singleflight_and_ttl():
    from bot.services.remnawave_system import RemnawaveSystemMixin

    class DummyClient(RemnawaveSystemMixin):
        def __init__(self):
            self.nodes_calls = 0

        async def get_nodes(self):
            self.nodes_calls += 1
            await asyncio.sleep(0.02)
            return []

        async def get_all_panel_users(self):
            return []

    client = DummyClient()
    res1, res2 = await asyncio.gather(
        client.get_live_sessions_explorer(ttl_seconds=10.0),
        client.get_live_sessions_explorer(ttl_seconds=10.0),
    )
    assert client.nodes_calls == 1
    assert res1 is res2

    # Subsequent warm hit still uses cache
    res3 = await client.get_live_sessions_explorer(ttl_seconds=10.0)
    assert client.nodes_calls == 1
    assert res3 is res1

    # Direct user connection endpoint 404 falls back cleanly to cached explorer without repeat 404 probes
    mock_http = AsyncMock()
    mock_http.get.return_value = MagicMock(status_code=404)
    client._client = mock_http
    s1 = await client.get_user_live_sessions(42)
    assert s1["isOnline"] is False
    assert client._direct_user_conn_supported is False
    calls_after_first = mock_http.get.await_count
    s2 = await client.get_user_live_sessions(42)
    assert s2["isOnline"] is False
    assert mock_http.get.await_count == calls_after_first


@pytest.mark.anyio
async def test_overview_bandwidth_series_capped():
    from bot.web.admin_overview_charts import _MAX_BW_SERIES_USERS, _fetch_user_bandwidth_series

    panel_users = [{"id": i, "usedTrafficBytes": 1000 + i} for i in range(1, _MAX_BW_SERIES_USERS + 25)]
    mock_rw = MagicMock()
    mock_rw.get_user_bandwidth_stats = AsyncMock(return_value=[])

    await _fetch_user_bandwidth_series(mock_rw, panel_users, "2026-01-01", "2026-01-07")
    assert mock_rw.get_user_bandwidth_stats.await_count == _MAX_BW_SERIES_USERS


@pytest.mark.anyio
async def test_admin_users_reuses_bulk_panel_without_n_plus_1(session_factory):
    from aiohttp.test_utils import make_mocked_request

    import bot.web.admin_users_list as aul
    from bot.db.models import User
    from bot.web.admin_users_list import get_admin_users

    aul._ONLINE_CACHE = (set(), set(), 0.0)

    async with session_factory() as session:
        session.add(User(telegram_id=10001, username="alice"))
        session.add(User(telegram_id=10002, username="bob"))
        await session.commit()

    mock_rw = MagicMock()
    mock_rw.get_all_panel_users = AsyncMock(return_value=[
        {"id": 1, "telegramId": 10001, "username": "alice_rw", "status": "ACTIVE", "usedTrafficBytes": 0},
        {"id": 2, "telegramId": 10002, "username": "bob_rw", "status": "ACTIVE", "usedTrafficBytes": 0},
    ])
    mock_rw.get_users_by_telegram_id = AsyncMock(return_value=[])
    mock_rw.get_active_sessions = AsyncMock(return_value=[])
    mock_rw.get_all_hwid_devices = AsyncMock(return_value=[])
    mock_rw.get_live_sessions_explorer = AsyncMock(return_value={"all_online_users": []})

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "remnawave": mock_rw,
    }
    req = make_mocked_request("GET", "/api/admin/users?user_id=99999&filter=all", app=app)
    resp = await get_admin_users(req)
    assert resp.status == 200
    payload = json.loads(resp.text)
    assert payload["ok"] is True
    assert len(payload["users"]) == 2
    assert mock_rw.get_all_panel_users.await_count == 1
    assert mock_rw.get_users_by_telegram_id.await_count == 0


@pytest.mark.anyio
async def test_rate_limit_middleware_redis_and_fallback():
    from aiogram.types import Update

    from bot.middlewares.rate_limit import MAX_EVENTS, RateLimitMiddleware, _buckets

    _buckets.pop(55667788, None)

    mock_pipe = MagicMock()
    mock_pipe.incr = MagicMock()
    mock_pipe.ttl = MagicMock()
    mock_pipe.execute = AsyncMock(return_value=[MAX_EVENTS + 1, 45])

    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipe)
    mock_redis.expire = AsyncMock()

    mw = RateLimitMiddleware(redis_client=mock_redis)
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Update)
    event.message = MagicMock()
    event.message.from_user = MagicMock(id=55667788, language_code="fa")

    res = await mw(handler, event, {})
    assert res is None
    assert not handler.called
    assert len(_buckets[55667788]) == 0
    _buckets.pop(55667788, None)


@pytest.mark.anyio
async def test_cross_surface_user_action_lock():
    from bot.handlers.shop_purchase import _PURCHASE_LOCKS
    from bot.web.cache import FastCache, user_action_lock

    _PURCHASE_LOCKS.discard(771122)
    cache = FastCache(redis_client=None)

    async with user_action_lock(cache, 771122, "purchase", ttl_seconds=30, local_locks=_PURCHASE_LOCKS) as acq1:
        assert acq1 is True
        async with user_action_lock(cache, 771122, "purchase", ttl_seconds=30) as acq2:
            assert acq2 is False

    # Re-acquiring succeeds after exit
    async with user_action_lock(cache, 771122, "purchase", ttl_seconds=30) as acq3:
        assert acq3 is True


@pytest.mark.anyio
async def test_bot_broadcast_background_and_redis_revoke(monkeypatch):
    from bot.handlers.admin_broadcast import (
        _BACKGROUND_TASKS,
        ACTIVE_BROADCASTS,
        broadcast_revoke_handler,
        broadcast_send,
    )
    from bot.web.cache import FastCache

    monkeypatch.setattr("bot.handlers.admin_broadcast._is_admin", lambda uid: uid == 99999)
    ACTIVE_BROADCASTS.clear()
    cache = FastCache(redis_client=None)
    bot = MagicMock()
    bot.cache = cache
    bot.edit_message_text = AsyncMock()
    bot.send_message = AsyncMock(
        side_effect=[MagicMock(message_id=100 + i) for i in range(1, 10)]
    )
    bot.delete_message = AsyncMock()
    bot.session_factory = None

    user_repo = MagicMock()
    user_repo.get_or_create = AsyncMock(
        return_value=MagicMock(telegram_id=99999, language="fa", menu_message_id=None)
    )
    user_repo.set_menu_message_id = AsyncMock()
    session = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "draft": "hello",
        "photo_id": None,
        "recipient_ids": [201, 202],
        "bcast_target": "all",
    })
    call = MagicMock()
    call.from_user = MagicMock(id=99999, username="admin")
    call.answer = AsyncMock()

    await broadcast_send(call, bot, user_repo, session, state)
    assert len(ACTIVE_BROADCASTS) == 1
    bcast_id = next(iter(ACTIVE_BROADCASTS))

    # Wait for spawned background task
    if _BACKGROUND_TASKS:
        await asyncio.gather(*list(_BACKGROUND_TASKS), return_exceptions=True)

    assert ACTIVE_BROADCASTS[bcast_id]["status"] == "finished"
    assert ACTIVE_BROADCASTS[bcast_id]["ok"] == 2

    # Simulate container restart (memory cleared) -> revoke reloads sent message list from FastCache
    ACTIVE_BROADCASTS.clear()
    rev_call = MagicMock()
    rev_call.from_user = MagicMock(id=99999)
    rev_call.data = f"adm:bcast:del:{bcast_id}"
    rev_call.answer = AsyncMock()

    await broadcast_revoke_handler(rev_call, bot, user_repo)
    assert bot.delete_message.await_count == 2
    assert ACTIVE_BROADCASTS[bcast_id]["status"] == "revoked"
    ACTIVE_BROADCASTS.clear()


@pytest.mark.anyio
async def test_support_chat_ssot_concurrent_append_bounded():
    from bot.services.support_chat import (
        MAX_CHAT_MESSAGES,
        append_support_message,
        get_active_thread_ids,
        get_support_messages,
    )
    from bot.web.cache import FastCache

    cache = FastCache(redis_client=None)
    await asyncio.gather(*[
        append_support_message(445566, sender="user", text=f"msg-{i}", msg_id=f"m{i}", cache=cache)
        for i in range(60)
    ])
    msgs = await get_support_messages(445566, cache=cache)
    assert len(msgs) == MAX_CHAT_MESSAGES
    assert 445566 in await get_active_thread_ids(cache=cache)


@pytest.mark.anyio
async def test_store_logo_upload_pillow_validation_and_persisted_serving(session_factory, tmp_path, monkeypatch):
    from aiohttp.test_utils import make_mocked_request

    from bot.web.admin_settings_api import post_admin_upload_store_logo
    from bot.web.server import serve_media_upload

    monkeypatch.chdir(tmp_path)

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "uploads_dir": tmp_path / "data" / "uploads",
    }

    # 1. Invalid spoofed non-image bytes rejected
    req_bad = make_mocked_request("POST", "/api/admin/settings/upload-logo?user_id=99999", headers={"Content-Type": "application/json"}, app=app)
    req_bad.json = AsyncMock(return_value={"logo_image": "data:image/png;base64," + base64.b64encode(b"<svg>xss</svg>").decode()})
    resp_bad = await post_admin_upload_store_logo(req_bad)
    assert resp_bad.status == 400

    # 2. Valid Pillow PNG accepted and saved in data/uploads/
    buf = BytesIO()
    Image.new("RGB", (8, 8), color=(10, 120, 200)).save(buf, format="PNG")
    png_bytes = buf.getvalue()

    req_ok = make_mocked_request("POST", "/api/admin/settings/upload-logo?user_id=99999", headers={"Content-Type": "application/json"}, app=app)
    req_ok.json = AsyncMock(return_value={"logo_image": "data:image/png;base64," + base64.b64encode(png_bytes).decode()})
    resp_ok = await post_admin_upload_store_logo(req_ok)
    assert resp_ok.status == 200
    body_ok = json.loads(resp_ok.text)
    assert body_ok["logo_url"].startswith("/media/uploads/store_logo.png?v=")
    assert (tmp_path / "data" / "uploads" / "store_logo.png").is_file()

    # 3. Persisted media route serves image & rejects path traversal
    req_get = make_mocked_request("GET", "/media/uploads/store_logo.png", match_info={"filename": "store_logo.png"}, app=app)
    resp_get = await serve_media_upload(req_get)
    assert resp_get.status == 200
    assert resp_get.body == png_bytes

    req_trav = make_mocked_request("GET", "/media/uploads/../.env", match_info={"filename": "../.env"}, app=app)
    resp_trav = await serve_media_upload(req_trav)
    assert resp_trav.status == 404


@pytest.mark.anyio
async def test_resolved_topup_cleans_local_receipt_when_telegram_file_id_exists(session_factory, tmp_path, monkeypatch):
    from aiohttp.test_utils import make_mocked_request

    from bot.db.models import Topup, User
    from bot.web.admin_topups import post_admin_topup_action

    monkeypatch.chdir(tmp_path)
    receipts_dir = tmp_path / "data" / "receipts"
    receipts_dir.mkdir(parents=True)

    async with session_factory() as session:
        session.add(User(telegram_id=5050, username="topup_user"))
        await session.flush()
        t = Topup(telegram_id=5050, amount=50000, receipt_photo_id="AgACAgQAAxkBAA_REAL_FILE_ID", status="pending")
        session.add(t)
        await session.commit()
        tid = t.id

    local_receipt = receipts_dir / f"receipt_{tid}.jpg"
    local_receipt.write_bytes(b"\xff\xd8\xff\xe0fake")
    assert local_receipt.exists()

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "bot": AsyncMock(),
        "settings": MagicMock(ADMIN_CHAT_ID=None),
    }
    req = make_mocked_request("POST", "/api/admin/topup/action?user_id=99999", app=app)
    req.json = AsyncMock(return_value={"topup_id": tid, "approved": True})
    resp = await post_admin_topup_action(req)
    assert resp.status == 200
    assert not local_receipt.exists()


@pytest.mark.anyio
async def test_alembic_baseline_covers_all_models(tmp_path):
    import sqlite3

    from alembic.config import Config

    import bot.db.models  # noqa: F401
    from alembic import command
    from bot.db.base import Base

    db_path = tmp_path / "alembic_test.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{str(db_path).replace(chr(92), '/')}")
    await asyncio.to_thread(command.upgrade, cfg, "head")

    con = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        con.close()

    missing = set(Base.metadata.tables.keys()) - tables
    assert not missing, f"Alembic baseline missing model tables: {missing}"


def test_compose_secrets_and_main_lifecycle_hardening():
    compose_txt = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD:-remnabot" not in compose_txt
    assert "REDIS_PASSWORD:-remnabot_redis_secret" not in compose_txt
    assert ":?Set POSTGRES_PASSWORD in .env" in compose_txt
    assert ":?Set REDIS_PASSWORD in .env" in compose_txt

    main_txt = Path("bot/main.py").read_text(encoding="utf-8")
    assert "Failed to start TMA web server; aborting startup" in main_txt
    assert "asyncio.gather(*tasks_to_drain, return_exceptions=True)" in main_txt
