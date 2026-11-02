"""Tests for Remnawave connection-keys endpoint integration and Custom Plan Tiered Volume Pricing."""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from bot.web.user_shop import compute_custom_plan_price, post_user_custom_plan_calculate


def test_compute_custom_plan_price_default_tiers():
    settings = SimpleNamespace(
        custom_plan_price_per_gb=1000,
        custom_plan_price_per_day=100,
        custom_plan_base_price=5000,
        custom_plan_volume_tiers_json="",
    )

    # 1. 30 GB (<= 50 GB) -> 0% volume discount
    # Traffic: 30,000, Days (30): 3,000, Base: 5,000 -> Total: 38,000
    raw, vol_pct, discounted = compute_custom_plan_price(30, 30, settings)
    assert vol_pct == 0
    assert raw == 38000
    assert discounted == 38000

    # 2. 80 GB (51 - 100 GB) -> 10% volume discount on traffic
    # Raw traffic: 80,000, 10% off -> 72,000. Days (30): 3,000, Base: 5,000 -> Total: 80,000
    raw, vol_pct, discounted = compute_custom_plan_price(80, 30, settings)
    assert vol_pct == 10
    assert raw == 88000
    assert discounted == 80000

    # 3. 150 GB (101 - 200 GB) -> 20% volume discount on traffic
    # Raw traffic: 150,000, 20% off -> 120,000. Days (30): 3,000, Base: 5,000 -> Total: 128,000
    raw, vol_pct, discounted = compute_custom_plan_price(150, 30, settings)
    assert vol_pct == 20
    assert raw == 158000
    assert discounted == 128000

    # 4. 300 GB (> 200 GB) -> 30% volume discount on traffic
    # Raw traffic: 300,000, 30% off -> 210,000. Days (60): 6,000, Base: 5,000 -> Total: 221,000
    raw, vol_pct, discounted = compute_custom_plan_price(300, 60, settings)
    assert vol_pct == 30
    assert raw == 311000
    assert discounted == 221000


def test_compute_custom_plan_price_custom_admin_tiers():
    custom_tiers = [
        {"min_gb": 1, "max_gb": 40, "discount_percent": 0},
        {"min_gb": 41, "max_gb": 90, "discount_percent": 15},
        {"min_gb": 91, "max_gb": 9999, "discount_percent": 35},
    ]
    settings = SimpleNamespace(
        custom_plan_price_per_gb=2000,
        custom_plan_price_per_day=200,
        custom_plan_base_price=0,
        custom_plan_volume_tiers_json=json.dumps(custom_tiers),
    )

    raw, vol_pct, discounted = compute_custom_plan_price(50, 10, settings)
    assert vol_pct == 15
    # Raw traffic: 100,000 -> 15% off = 85,000. Days: 2,000 -> Total: 87,000
    assert raw == 102000
    assert discounted == 87000

    raw, vol_pct, discounted = compute_custom_plan_price(100, 10, settings)
    assert vol_pct == 35
    # Raw traffic: 200,000 -> 35% off = 130,000. Days: 2,000 -> Total: 132,000
    assert raw == 202000
    assert discounted == 132000


@pytest.mark.anyio
async def test_remnawave_get_user_connection_keys():
    from bot.services.remnawave import RemnawaveClient

    client = RemnawaveClient(base_url="http://mock-panel", token="dummy-token")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "response": {
            "enabledKeys": [
                "vless://uuid@1.1.1.1:443?security=reality#Germany-1",
                "vmess://dummy-b64#Netherlands-1",
            ],
            "disabledKeys": [],
            "hiddenKeys": [],
        }
    }
    client._client.get = AsyncMock(return_value=mock_response)

    keys = await client.get_user_connection_keys(42)
    assert keys is not None
    assert len(keys) == 2
    assert "vless://" in keys[0]
    client._client.get.assert_called_once_with("/api/subscriptions/connection-keys/42")

    await client.close()
