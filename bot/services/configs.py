"""Service for fetching and parsing single configs from subscription URLs.

Supports Remnawave and standard v2ray subscription links:
- Decodes base64-encoded subscription strings, sing-box JSON, clash YAML, or plaintext config lines.
- Recognizes protocols: vless, vmess, trojan, ss, shadowsocks, hysteria2, hy2, tuic, wireguard, wg.
- Extracts user-friendly display names from URL fragments (#) or vmess JSON (ps).
"""
import asyncio
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
            clean = urllib.parse.unquote(text).strip().strip('"').strip("'")
            clean = "".join(clean.split()).replace("-", "+").replace("_", "/")
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


async def fetch_subscription_configs(url: str, timeout: float = 2.5) -> list[dict[str, str]]:
    """Download subscription content and return parsed configs with robust candidate fallback."""
    if not url or not url.startswith(("http://", "https://")):
        return []

    try:
        return await asyncio.wait_for(_fetch_subscription_configs_impl(url, timeout), timeout=5.5)
    except TimeoutError:
        logger.warning("Subscription fetch reached overall timeout for %s", url)
        return []
    except Exception as exc:
        logger.warning("Unexpected error during subscription fetch for %s: %s", url, exc)
        return []


async def _fetch_subscription_configs_impl(url: str, timeout: float = 2.5) -> list[dict[str, str]]:
    from bot.config import get_settings
    settings = get_settings()
    proxy = settings.IRAN_PROXY.strip() if getattr(settings, "IRAN_PROXY", "") else None
    base_remna = (getattr(settings, "REMNAWAVE_BASE_URL", "") or getattr(settings, "REMNAWAVE_URL", "")).strip() if settings else ""

    candidate_urls: list[str] = [url]

    # Add /api/ variant of original URL
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
    elif parsed_u.path.startswith("/api/sub/"):
        candidate_urls.append(urllib.parse.urlunparse((
            parsed_u.scheme,
            parsed_u.netloc,
            parsed_u.path.replace("/api/sub/", "/sub/"),
            "",
            parsed_u.query,
            "",
        )))

    # If base_remna is configured and host differs, add internal panel rewrite as fallback
    if base_remna:
        parsed_orig = urllib.parse.urlparse(url)
        parsed_base = urllib.parse.urlparse(base_remna)
        if parsed_orig.netloc.lower() != parsed_base.netloc.lower():
            orig_path = parsed_orig.path or ""
            if orig_path.startswith("/api/sub/"):
                api_path = orig_path
            elif orig_path.startswith("/sub/"):
                api_path = "/api" + orig_path
            else:
                clean_seg = orig_path.lstrip("/")
                api_path = f"/api/sub/{clean_seg}"

            candidate_urls.append(urllib.parse.urlunparse((
                parsed_base.scheme,
                parsed_base.netloc,
                api_path,
                "",
                parsed_orig.query,
                "",
            )))

    # Deduplicate while preserving order
    seen_urls: set[str] = set()
    deduped_candidates: list[str] = []
    for c_url in candidate_urls:
        if c_url and c_url not in seen_urls:
            seen_urls.add(c_url)
            deduped_candidates.append(c_url)

    primary_ua = "v2rayNG/1.8.5"
    fallback_uas = ["Shadowrocket/1982", "v2ray"]

    for target_url in deduped_candidates:
        parsed = urllib.parse.urlparse(target_url)
        is_internal = parsed.hostname in ("127.0.0.1", "localhost", "remnawave") or (
            parsed.hostname and (parsed.hostname.startswith("172.") or parsed.hostname.startswith("192.168.") or parsed.hostname.startswith("10."))
        )

        attempts = [None]
        if proxy and not is_internal:
            attempts = [None, proxy]

        for p in attempts:
            try:
                resp = None
                try:
                    async with httpx.AsyncClient(verify=True, follow_redirects=True, timeout=timeout, proxy=p) as client:
                        resp = await client.get(target_url, headers={"User-Agent": primary_ua, "Accept": "*/*"})
                except Exception as cert_err:
                    logger.debug("SSL verify=True failed for %s (%s), retrying with verify=False", target_url, cert_err)
                    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=timeout, proxy=p) as client:
                        resp = await client.get(target_url, headers={"User-Agent": primary_ua, "Accept": "*/*"})

                if resp is not None and resp.status_code == 200 and resp.text.strip():
                    text_body = resp.text.strip()
                    if not text_body.lower().startswith(("<!doctype", "<html")):
                        configs = parse_subscription_text(text_body)
                        if configs:
                            logger.info("Successfully fetched %d configs from %s", len(configs), target_url)
                            return configs
                elif resp is not None and resp.status_code in (403, 406):
                    for alt_ua in fallback_uas:
                        alt_resp = None
                        try:
                            async with httpx.AsyncClient(verify=True, follow_redirects=True, timeout=timeout, proxy=p) as client:
                                alt_resp = await client.get(target_url, headers={"User-Agent": alt_ua, "Accept": "*/*"})
                        except Exception:
                            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=timeout, proxy=p) as client:
                                alt_resp = await client.get(target_url, headers={"User-Agent": alt_ua, "Accept": "*/*"})
                        if alt_resp and alt_resp.status_code == 200 and alt_resp.text.strip():
                            text_body = alt_resp.text.strip()
                            if not text_body.lower().startswith(("<!doctype", "<html")):
                                configs = parse_subscription_text(text_body)
                                if configs:
                                    return configs
            except Exception as exc:
                logger.warning("Subscription attempt failed for %s (proxy=%s): %s", target_url, p, exc)

    return []
