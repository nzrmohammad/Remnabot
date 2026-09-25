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
        except Exception:
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
            except Exception:
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
    """Download subscription content and return parsed configs."""
    if not url or not url.startswith(("http://", "https://")):
        return []

    headers = {
        "User-Agent": "v2rayNG/1.8.5",
        "Accept": "*/*",
    }
    try:
        async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("Subscription fetch failed: HTTP %s for %s", resp.status_code, url)
                return []
            return parse_subscription_text(resp.text)
    except Exception as exc:
        logger.warning("Subscription fetch exception for %s: %s", url, exc)
        return []
