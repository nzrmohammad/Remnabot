"""Service for fetching and parsing single configs from subscription URLs.

Supports Remnawave and standard v2ray subscription links:
- Decodes base64-encoded subscription strings, sing-box JSON, or plaintext config lines.
- Recognizes protocols: vless, vmess, trojan, ss, shadowsocks, hysteria2, hy2, tuic, wireguard, wg.
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
    "shadowsocks://",
    "hysteria://",
    "hysteria2://",
    "hy2://",
    "tuic://",
    "wireguard://",
    "wg://",
    "socks5://",
    "socks://",
)


def parse_subscription_text(text: str) -> list[dict[str, str]]:
    """Parse raw subscription content (base64, JSON, or plaintext) into configs list."""
    if not text:
        return []

    text = text.strip().lstrip("\ufeff")
    if not text:
        return []

    # 1. Attempt JSON parsing (e.g. sing-box or raw JSON array/dict)
    if text.startswith(("{", "[")):
        try:
            parsed_json = json.loads(text)
            if isinstance(parsed_json, list):
                json_lines = []
                for item in parsed_json:
                    if isinstance(item, str) and "://" in item:
                        json_lines.append(item.strip())
                    elif isinstance(item, dict) and item.get("uri"):
                        json_lines.append(str(item["uri"]).strip())
                if json_lines:
                    text = "\n".join(json_lines)
            elif isinstance(parsed_json, dict):
                outbounds = parsed_json.get("outbounds") or []
                extracted_cfgs: list[dict[str, str]] = []
                for idx, ob in enumerate(outbounds, start=1):
                    ob_type = str(ob.get("type", "")).lower()
                    if ob_type in ("vless", "vmess", "trojan", "shadowsocks", "hysteria2", "tuic", "wireguard"):
                        tag = ob.get("tag") or ob.get("server") or f"{ob_type.upper()} {idx}"
                        extracted_cfgs.append({
                            "name": tag,
                            "protocol": ob_type,
                            "uri": f"{ob_type}://{ob.get('server', '')}:{ob.get('server_port', '')}#{urllib.parse.quote(tag)}",
                        })
                if extracted_cfgs:
                    return extracted_cfgs
        except Exception as exc:
            logger.debug("Subscription JSON parse attempt skipped: %s", exc)

    raw_lines = [line.strip().lstrip("\ufeff") for line in text.splitlines() if line.strip()]
    lines: list[str] = []

    # Check if raw text already has protocol schemes
    is_plain = any(any(line.lower().startswith(p) for p in SUPPORTED_PROTOCOLS) for line in raw_lines)

    if not is_plain:
        try:
            clean = "".join(text.split()).replace("-", "+").replace("_", "/")
            clean += "=" * (-len(clean) % 4)
            decoded = base64.b64decode(clean).decode("utf-8", errors="replace").lstrip("\ufeff")
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
                payload = line[8:].strip().replace("-", "+").replace("_", "/")
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


async def fetch_subscription_configs(url: str, timeout: float = 4.0) -> list[dict[str, str]]:
    """Download subscription content and return parsed configs with proxy & multi-UA resilience."""
    if not url or not url.startswith(("http://", "https://")):
        return []

    from bot.config import get_settings
    settings = get_settings()
    proxy = settings.IRAN_PROXY.strip() if getattr(settings, "IRAN_PROXY", "") else None
    base_remna = getattr(settings, "REMNAWAVE_URL", "").strip() if settings else ""

    # Candidate URLs (Original URL + rewritten panel URL if available)
    candidate_urls = [url]
    if base_remna:
        parsed_orig = urllib.parse.urlparse(url)
        parsed_base = urllib.parse.urlparse(base_remna)
        if parsed_orig.netloc != parsed_base.netloc:
            rewritten = urllib.parse.urlunparse((
                parsed_base.scheme,
                parsed_base.netloc,
                parsed_orig.path,
                parsed_orig.params,
                parsed_orig.query,
                parsed_orig.fragment,
            ))
            candidate_urls.append(rewritten)

    user_agents = [
        "v2rayNG/1.8.5",
        "v2rayNG",
        "ClashMeta",
    ]

    for target_url in candidate_urls:
        parsed = urllib.parse.urlparse(target_url)
        is_internal = parsed.hostname in ("127.0.0.1", "localhost", "remnawave") or (
            parsed.hostname and (parsed.hostname.startswith("172.") or parsed.hostname.startswith("192.168.") or parsed.hostname.startswith("10."))
        )

        attempts = [None]
        if proxy and not is_internal:
            attempts = [proxy, None]

        for ua in user_agents:
            headers = {
                "User-Agent": ua,
                "Accept": "*/*",
            }
            for p in attempts:
                try:
                    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=timeout, proxy=p) as client:
                        resp = await client.get(target_url, headers=headers)
                        if resp.status_code == 200 and resp.text.strip():
                            configs = parse_subscription_text(resp.text)
                            if configs:
                                return configs
                except Exception as exc:
                    logger.debug("Subscription fetch attempt failed (url=%s, ua=%s, proxy=%s): %s", target_url, ua, p, exc)

    return []
