"""Service for fetching and parsing single configs from subscription URLs.

Supports Remnawave and standard v2ray subscription links:
- Decodes base64-encoded subscription strings or parses plaintext config lines.
- Recognizes protocols: vless, vmess, trojan, ss, hysteria2, hy2, tuic, wireguard.
- Extracts user-friendly display names from URL fragments (#) or vmess JSON (ps).
"""
import base64
import json
import logging
import urllib.parse
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUPPORTED_PROTOCOLS = (
    "vless://",
    "vmess://",
    "trojan://",
    "ss://",
    "hysteria2://",
    "hy2://",
    "tuic://",
    "wireguard://",
)


def parse_subscription_text(text: str) -> list[dict[str, str]]:
    """Parse raw subscription content (base64 or plaintext) into configs list."""
    if not text:
        return []

    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    lines: list[str] = []

    # Check if raw text already has protocol schemes
    is_plain = any(any(line.lower().startswith(p) for p in SUPPORTED_PROTOCOLS) for line in raw_lines)

    if not is_plain:
        try:
            clean = text.strip().replace("\r", "").replace("\n", "")
            clean += "=" * (-len(clean) % 4)
            decoded = base64.b64decode(clean).decode("utf-8", errors="replace")
            lines = [line.strip() for line in decoded.splitlines() if line.strip()]
        except Exception as exc:
            logger.warning("Base64 decoding failed for configs: %s", exc)
            lines = raw_lines
    else:
        lines = raw_lines

    configs: list[dict[str, str]] = []
    for idx, line in enumerate(lines, start=1):
        if not line or "://" not in line:
            continue
        proto = line.split("://", 1)[0].lower()

        name = ""
        if proto == "vmess":
            try:
                payload = line[8:].strip()
                payload += "=" * (-len(payload) % 4)
                data: dict[str, Any] = json.loads(
                    base64.b64decode(payload).decode("utf-8", errors="replace")
                )
                name = str(data.get("ps") or data.get("add") or f"VMess {idx}")
            except Exception as exc:
                logger.warning("VMess JSON parsing failed for config %d: %s", idx, exc)
                name = f"VMess {idx}"
        else:
            if "#" in line:
                raw_name = line.split("#", 1)[1]
                name = urllib.parse.unquote(raw_name).strip()
            if not name:
                name = f"{proto.upper()} {idx}"

        configs.append({
            "name": name,
            "protocol": proto,
            "uri": line,
        })

    return configs


async def fetch_subscription_configs(url: str, timeout: float = 10.0) -> list[dict[str, str]]:
    """Download subscription content and return parsed configs with proxy & multi-UA resilience."""
    if not url or not url.startswith(("http://", "https://")):
        return []

    from bot.config import get_settings
    settings = get_settings()
    proxy = settings.IRAN_PROXY.strip() if getattr(settings, "IRAN_PROXY", "") else None

    user_agents = [
        "v2rayNG/1.8.5",
        "ClashMeta",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    ]

    for ua in user_agents:
        headers = {
            "User-Agent": ua,
            "Accept": "*/*",
        }
        attempts = [None]
        if proxy:
            attempts.append(proxy)
        for p in attempts:
            try:
                async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=timeout, proxy=p) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200 and resp.text.strip():
                        configs = parse_subscription_text(resp.text)
                        if configs:
                            return configs
            except Exception as exc:
                logger.debug("Subscription fetch attempt failed (ua=%s, proxy=%s): %s", ua, p, exc)

    return []
