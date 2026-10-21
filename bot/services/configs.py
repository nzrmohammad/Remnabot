"""Service for fetching and parsing single configs from subscription URLs.

Supports Remnawave and standard v2ray subscription links:
- Decodes base64-encoded subscription strings, sing-box JSON, clash YAML, or plaintext config lines.
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


def _parse_json_subscription(text: str) -> list[dict[str, str]] | None:
    """Parse Sing-box JSON or JSON array/dict of configs."""
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
                return parse_subscription_text("\n".join(json_lines))
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
    return None


def _parse_clash_yaml(text: str) -> list[dict[str, str]] | None:
    """Parse Clash / Meta YAML proxies list."""
    if "proxies:" not in text and "proxy-groups:" not in text:
        return None
    try:
        clash_cfgs: list[dict[str, str]] = []
        current: dict[str, str] = {}
        for line in text.splitlines():
            line_str = line.strip()
            if line_str.startswith("- name:") or line_str.startswith("- {name:"):
                if current.get("name") and (current.get("type") or current.get("server")):
                    clash_cfgs.append(current)
                name_part = line_str.split("name:", 1)[1].split(",")[0].strip().strip('"').strip("'")
                current = {"name": name_part}
            elif ":" in line_str and current:
                parts = line_str.split(":", 1)
                k = parts[0].strip().lstrip("-").strip().lower()
                v = parts[1].strip().split(",")[0].strip().strip('"').strip("'")
                if k in ("type", "server", "port", "uuid", "password"):
                    current[k] = v
        if current.get("name") and (current.get("type") or current.get("server")):
            clash_cfgs.append(current)

        if clash_cfgs:
            extracted_yaml: list[dict[str, str]] = []
            for idx, c in enumerate(clash_cfgs, start=1):
                p_type = c.get("type", "vpn").lower()
                p_name = c.get("name", f"Server {idx}")
                p_server = c.get("server", "")
                p_port = c.get("port", "")
                uri = f"{p_type}://{p_server}:{p_port}#{urllib.parse.quote(p_name)}" if p_server else ""
                extracted_yaml.append({
                    "name": p_name,
                    "protocol": p_type,
                    "uri": uri,
                })
            return extracted_yaml
    except Exception as exc:
        logger.debug("Clash YAML parse attempt skipped: %s", exc)
    return None


def parse_subscription_text(text: str) -> list[dict[str, str]]:
    """Parse raw subscription content (base64, JSON, Clash YAML, or plaintext) into configs list."""
    if not text:
        return []

    text = text.strip().lstrip("\ufeff")
    if not text:
        return []

    # 1. Attempt JSON parsing (e.g. sing-box or raw JSON array/dict)
    if text.startswith(("{", "[")):
        json_cfgs = _parse_json_subscription(text)
        if json_cfgs:
            return json_cfgs

    # 2. Attempt Clash YAML parsing
    clash_cfgs = _parse_clash_yaml(text)
    if clash_cfgs:
        return clash_cfgs

    raw_lines = [line.strip().lstrip("\ufeff") for line in text.splitlines() if line.strip()]
    lines: list[str] = []

    # Check if raw text already has protocol schemes
    is_plain = any(any(line.lower().startswith(p) for p in SUPPORTED_PROTOCOLS) for line in raw_lines)

    if not is_plain:
        try:
            clean = "".join(text.split()).replace("-", "+").replace("_", "/")
            clean = urllib.parse.unquote(clean).strip().strip('"').strip("'")
            clean += "=" * (-len(clean) % 4)
            decoded = base64.b64decode(clean).decode("utf-8", errors="replace").lstrip("\ufeff").strip()

            # Check if decoded is JSON or Clash YAML
            if decoded.startswith(("{", "[")):
                json_res = _parse_json_subscription(decoded)
                if json_res:
                    return json_res
            if "proxies:" in decoded:
                clash_res = _parse_clash_yaml(decoded)
                if clash_res:
                    return clash_res

            lines = [line.strip() for line in decoded.splitlines() if line.strip()]
        except Exception as exc:
            logger.warning("Base64 decoding failed for configs: %s", exc)
            lines = raw_lines
    else:
        lines = raw_lines

    configs: list[dict[str, str]] = []
    for idx, line in enumerate(lines, start=1):
        if not line or line.startswith("#") or "://" not in line:
            continue
        proto = line.split("://", 1)[0].lower()

        name = ""
        if proto == "vmess":
            try:
                payload = line[8:].strip().replace("-", "+").replace("_", "/")
                payload = urllib.parse.unquote(payload)
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


async def fetch_subscription_configs(url: str, timeout: float = 3.5) -> list[dict[str, str]]:
    """Download subscription content and return parsed configs with internal rewrite & multi-UA resilience."""
    if not url or not url.startswith(("http://", "https://")):
        return []

    from bot.config import get_settings
    settings = get_settings()
    proxy = settings.IRAN_PROXY.strip() if getattr(settings, "IRAN_PROXY", "") else None
    base_remna = getattr(settings, "REMNAWAVE_URL", "").strip() if settings else ""

    candidate_urls: list[str] = []

    # If base_remna is configured, build internal panel URLs FIRST (avoids Cloudflare / GFW loopbacks)
    if base_remna:
        parsed_orig = urllib.parse.urlparse(url)
        parsed_base = urllib.parse.urlparse(base_remna)

        orig_path = parsed_orig.path or ""
        # Check /api/sub vs /sub variants
        api_path = orig_path if orig_path.startswith("/api/sub/") else ("/api" + orig_path if orig_path.startswith("/sub/") else orig_path)
        sub_path = orig_path.replace("/api/sub/", "/sub/") if orig_path.startswith("/api/sub/") else orig_path

        rewritten_api = urllib.parse.urlunparse((
            parsed_base.scheme,
            parsed_base.netloc,
            api_path,
            "",
            parsed_orig.query,
            "",
        ))
        rewritten_sub = urllib.parse.urlunparse((
            parsed_base.scheme,
            parsed_base.netloc,
            sub_path,
            "",
            parsed_orig.query,
            "",
        ))

        candidate_urls.extend([rewritten_api, rewritten_sub])

    # Also add the original URL and its /api/ variant
    candidate_urls.append(url)
    parsed_u = urllib.parse.urlparse(url)
    if parsed_u.path.startswith("/sub/"):
        candidate_urls.append(urllib.parse.urlunparse((
            parsed_u.scheme,
            parsed_u.netloc,
            "/api" + parsed_u.path,
            "",
            parsed_u.query,
            "",
        )))

    # Deduplicate while preserving order
    seen_urls: set[str] = set()
    deduped_candidates: list[str] = []
    for c_url in candidate_urls:
        if c_url and c_url not in seen_urls:
            seen_urls.add(c_url)
            deduped_candidates.append(c_url)

    user_agents = [
        "v2rayNG/1.8.5",
        "Shadowrocket/1982",
        "v2ray",
    ]

    for target_url in deduped_candidates:
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
                "Accept": "text/plain, application/octet-stream, */*",
            }
            for p in attempts:
                try:
                    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=timeout, proxy=p) as client:
                        resp = await client.get(target_url, headers=headers)
                        if resp.status_code == 200 and resp.text.strip():
                            # Skip if response is HTML web application
                            text_body = resp.text.strip()
                            if text_body.lower().startswith(("<!doctype", "<html")):
                                continue
                            configs = parse_subscription_text(text_body)
                            if configs:
                                logger.info("Successfully fetched %d configs from %s", len(configs), target_url)
                                return configs
                except Exception as exc:
                    logger.debug("Subscription fetch attempt failed (url=%s, ua=%s, proxy=%s): %s", target_url, ua, p, exc)

    return []
