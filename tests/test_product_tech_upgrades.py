"""Regression tests for Product & Technical Upgrade Ideas #1 to #4."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.anyio
async def test_task_queue_checkpoint_and_restart_recovery():
    from bot.handlers.admin_broadcast import ACTIVE_BROADCASTS
    from bot.services.task_queue import (
        QUEUE_ACTIVE_SET_KEY,
        execute_broadcast_job,
        recover_pending_broadcasts,
        request_job_stop,
        save_broadcast_job,
    )
    from bot.web.cache import FastCache

    ACTIVE_BROADCASTS.clear()
    cache = FastCache(redis_client=None)

    # 1. Resuming from cursor_idx=2 skips recipients 0 and 1
    job = {
        "job_id": "bc_resume_test_1",
        "kind": "bot",
        "admin_id": 99999,
        "target": "all",
        "target_label": "همه کاربران",
        "lang": "fa",
        "draft": "update",
        "text": "",
        "photo_id": None,
        "photo_raw": "",
        "recipient_ids": [11, 22, 33, 44],
        "cursor_idx": 2,
        "ok": 2,
        "fail": 0,
        "sent": [[11, 1], [22, 2]],
        "status": "running",
    }
    ACTIVE_BROADCASTS["bc_resume_test_1"] = {
        "status": "running",
        "sent": [(11, 1), (22, 2)],
        "ok": 2,
        "fail": 0,
        "total": 4,
        "target": "all",
        "admin_id": 99999,
    }

    bot = MagicMock()
    bot.cache = cache
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=99))
    result_job = await execute_broadcast_job(
        bot,
        job,
        cache=cache,
        in_memory_ref=ACTIVE_BROADCASTS["bc_resume_test_1"],
    )
    assert [call.kwargs["chat_id"] for call in bot.send_message.await_args_list] == [33, 44]
    assert result_job["ok"] == 4
    assert result_job["cursor_idx"] == 4
    assert result_job["status"] == "finished"

    # 2. Simulate Redis restart recovery on a queued job
    redis_mock = MagicMock()
    redis_mock.smembers = AsyncMock(return_value={b"web_rec_1"})
    redis_mock.sadd = AsyncMock()
    redis_mock.srem = AsyncMock()
    redis_mock.expire = AsyncMock()
    cache_rec = FastCache(redis_client=None)
    pending_job = {
        "job_id": "web_rec_1",
        "kind": "web",
        "admin_id": 99999,
        "target": "all",
        "target_label": "همه",
        "text": "<b>hello</b>",
        "photo_id": None,
        "photo_raw": "",
        "recipient_ids": [501, 502],
        "cursor_idx": 1,
        "ok": 1,
        "fail": 0,
        "sent": [[501, 10]],
        "status": "running",
    }
    await save_broadcast_job(cache_rec, pending_job)
    cache_rec._redis = redis_mock
    # Keep L1 memory only for get without calling redis.get mock unless needed
    redis_mock.get = AsyncMock(return_value=json.dumps(pending_job))

    bot2 = MagicMock()
    bot2.send_message = AsyncMock(return_value=MagicMock(message_id=200))
    resumed = await recover_pending_broadcasts(bot2, session_factory=None, cache=cache_rec)
    assert resumed == 1

    # Wait briefly for resumed task to complete
    from bot.services.task_queue import _ACTIVE_TASK_REGISTRY
    if _ACTIVE_TASK_REGISTRY:
        import asyncio
        await asyncio.gather(*list(_ACTIVE_TASK_REGISTRY), return_exceptions=True)
    assert bot2.send_message.await_count == 1
    assert bot2.send_message.await_args_list[0].kwargs["chat_id"] == 502

    # 3. Redis stop flag halts queue job
    await request_job_stop(cache_rec, "stop_test_1")
    assert QUEUE_ACTIVE_SET_KEY == "queue:broadcast:active"
    ACTIVE_BROADCASTS.clear()


@pytest.mark.anyio
async def test_panel_snapshot_reuse_in_overview_and_charts(session_factory):
    from bot.db.repositories.traffic_snapshot_repo import TrafficSnapshotRepository
    from bot.services.panel_snapshot import get_cached_panel_snapshot, refresh_panel_snapshot
    from bot.web.admin_overview import _fetch_and_build_overview
    from bot.web.cache import FastCache

    cache = FastCache(redis_client=None)
    mock_rw = MagicMock()
    mock_rw.get_nodes = AsyncMock(return_value=[{"uuid": "n1", "name": "DE", "isConnected": True, "isDisabled": False, "countryCode": "DE", "trafficUsedBytes": 10 * 1024**3}])
    mock_rw.get_all_panel_users = AsyncMock(return_value=[{"id": 1, "status": "ACTIVE", "usedTrafficBytes": 5 * 1024**3}])
    mock_rw.get_hwid_stats = AsyncMock(return_value={"online_devices": 1})
    mock_rw.get_user_bandwidth_stats = AsyncMock(return_value=[])

    snap = await refresh_panel_snapshot(mock_rw, cache, warm_charts=True)
    assert snap["healthy"] is True
    assert snap["nodes_online"] == 1
    assert snap["panel_users_count"] == 1
    bw_calls_after_snap = mock_rw.get_user_bandwidth_stats.await_count

    # Record HourlyTrafficSnapshot row so charts read from DB instead of calling get_user_bandwidth_stats
    now_utc = datetime.now(timezone.utc)
    async with session_factory() as session:
        await TrafficSnapshotRepository(session).record_snapshot(
            timestamp=now_utc,
            total_bytes=20 * 1024**3,
            delta_bytes=4 * 1024**3,
        )
        await session.commit()

    # Now cached lookup hits FastCache (zero additional get_nodes/get_all_panel_users calls!)
    cached_snap = await get_cached_panel_snapshot(mock_rw, cache, force_refresh=False)
    assert cached_snap["nodes_online"] == 1
    assert mock_rw.get_nodes.await_count == 1
    assert mock_rw.get_all_panel_users.await_count == 1

    async with session_factory() as session:
        overview = await _fetch_and_build_overview(session, mock_rw, cache, now_utc, is_refresh=False)
        assert overview["metrics"]["total_panel_users"] == 1
        # Snapshot kept Remnawave HTTP calls at 0 during overview build (reused Redis/FastCache + HourlyTrafficSnapshot)
        assert mock_rw.get_nodes.await_count == 1
        assert mock_rw.get_all_panel_users.await_count == 1
        assert mock_rw.get_user_bandwidth_stats.await_count == bw_calls_after_snap


@pytest.mark.anyio
async def test_mobile_perf_lazy_chart_minifier_and_401_close_ux():
    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request

    from bot.web.server import serve_app_html

    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    assert "chart.umd.min.js" not in app_html
    assert "chart.umd.min.js" not in admin_html

    charts_js = Path("bot/web/static/js/charts.js").read_text(encoding="utf-8")
    assert "window.ensureChart = ensureChart" in charts_js

    api_js = Path("bot/web/static/js/api.js").read_text(encoding="utf-8")
    assert "notifySessionExpired" in api_js
    assert "window.Telegram?.WebApp?.close" in api_js

    # Verify JS minifier script runs cleanly and produces valid minified files
    res = subprocess.run(["node", "scripts/build_assets.mjs"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr or res.stdout
    assert (Path("bot/web/static/js/dist/app.min.js")).is_file()

    # In non-dev mode, serve_app_html automatically references minified bundles
    app = web.Application()
    app["is_dev"] = False
    req = make_mocked_request("GET", "/app", app=app)
    resp = await serve_app_html(req)
    assert resp.status == 200
    assert "/static/js/dist/app.min.js?v=" in resp.text


@pytest.mark.anyio
async def test_system_health_reconciliation_and_5xx_spike_alert(session_factory, tmp_path):
    from aiohttp.test_utils import make_mocked_request

    from bot.db.models import Order
    from bot.services.system_health import record_api_error_spike
    from bot.web.admin_health_api import get_admin_system_health, post_admin_reconcile_run
    from bot.web.cache import FastCache

    cache = FastCache(redis_client=None)
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=30)

    async with session_factory() as session:
        # 1. Stale pending order
        session.add(Order(telegram_id=6060, service_id=None, service_name="Plan A", amount=50000, status="pending", created_at=stale_time))
        # 2. Paid order whose panel_user_id is missing on Remnawave panel -> flagged in reconciliation audit
        session.add(Order(telegram_id=6061, service_id=None, service_name="Plan B", panel_user_id=999999, amount=90000, status="paid"))
        await session.commit()

    mock_rw = MagicMock()
    mock_rw.get_nodes = AsyncMock(return_value=[{"uuid": "n1", "isConnected": True, "isDisabled": False}])
    mock_rw.get_all_panel_users = AsyncMock(return_value=[{"id": 123, "status": "ACTIVE"}])
    mock_rw.get_hwid_stats = AsyncMock(return_value={})

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "cache": cache,
        "remnawave": mock_rw,
        "bot": mock_bot,
        "settings": MagicMock(ADMIN_CHAT_ID=777, ADMIN_TOPIC_ERRORS=5, BACKUP_PASSWORD="secret"),
    }

    req = make_mocked_request("GET", "/api/admin/system-health?user_id=99999&refresh=1", app=app)
    resp = await get_admin_system_health(req)
    assert resp.status == 200
    body = json.loads(resp.text)
    assert body["ok"] is True
    h = body["health"]
    assert h["db"]["ok"] is True
    assert h["remnawave"]["healthy"] is True
    assert h["reconciliation"]["stale_pending_orders"] == 1
    assert h["reconciliation"]["panel_mismatches_count"] == 1
    assert h["reconciliation"]["panel_mismatches"][0]["panel_user_id"] == "999999"

    # Trigger 1-click reconcile from admin health endpoint -> closes stale pending order
    req_rec = make_mocked_request("POST", "/api/admin/reconcile/run?user_id=99999", app=app)
    resp_rec = await post_admin_reconcile_run(req_rec)
    assert resp_rec.status == 200
    assert json.loads(resp_rec.text)["closed_count"] == 1

    mock_bot.send_message.reset_mock()
    # Verify 5xx spike threshold (>= 5 in 5m) dispatches single throttled alert
    for _ in range(4):
        assert await record_api_error_spike(mock_bot, session_factory, cache, status_code=500, path="/api/test") is False
    assert await record_api_error_spike(mock_bot, session_factory, cache, status_code=500, path="/api/test") is True
    assert await record_api_error_spike(mock_bot, session_factory, cache, status_code=502, path="/api/test") is False
    assert mock_bot.send_message.await_count == 1
