"""SSL Certificate Health and Expiry Checker for Nodes and Domains."""
import asyncio
import ipaddress
import logging
import socket
import ssl
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from bot.config import get_settings

logger = logging.getLogger(__name__)


def is_ip_address(host: str) -> bool:
    """Check if host string is an IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _check_domain_ssl_sync(domain: str, port: int = 443, timeout: float = 4.0) -> dict[str, Any]:
    """Synchronous SSL certificate inspection."""
    clean_host = domain.strip()
    if "://" in clean_host:
        parsed = urllib.parse.urlparse(clean_host)
        clean_host = parsed.hostname or clean_host
        if parsed.port:
            port = parsed.port

    if ":" in clean_host:
        parts = clean_host.split(":")
        clean_host = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            pass

    clean_host = clean_host.strip()
    if not clean_host or is_ip_address(clean_host):
        return {
            "domain": clean_host or domain,
            "port": port,
            "valid": False,
            "is_ip": True,
            "days_left": None,
            "expires_at": None,
            "issuer": None,
            "status": "skipped_ip",
            "error": "آدرس IP است و گواهی SSL دامنه ندارد.",
        }

    context = ssl.create_default_context()
    try:
        with socket.create_connection((clean_host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=clean_host) as ssock:
                cert = ssock.getpeercert()
                not_after_str = cert.get("notAfter")
                if not not_after_str:
                    return {
                        "domain": clean_host,
                        "port": port,
                        "valid": False,
                        "days_left": None,
                        "expires_at": None,
                        "issuer": None,
                        "status": "error",
                        "error": "تاریخ انقضای گواهی در دسترس نیست.",
                    }

                expire_date = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                days_left = (expire_date - now_utc).days

                issuer_dict = dict(x[0] for x in cert.get("issuer", ()))
                issuer = issuer_dict.get("organizationName") or issuer_dict.get("commonName") or "Unknown"

                if days_left < 0:
                    status = "expired"
                elif days_left <= 3:
                    status = "critical"
                elif days_left <= 14:
                    status = "warning"
                else:
                    status = "ok"

                return {
                    "domain": clean_host,
                    "port": port,
                    "valid": True,
                    "is_ip": False,
                    "days_left": max(0, days_left),
                    "expires_at": expire_date.strftime("%Y-%m-%d"),
                    "issuer": issuer,
                    "status": status,
                    "error": None,
                }
    except ssl.SSLCertVerificationError as exc:
        return {
            "domain": clean_host,
            "port": port,
            "valid": False,
            "is_ip": False,
            "days_left": 0,
            "expires_at": None,
            "issuer": None,
            "status": "invalid",
            "error": f"گواهی نامعتبر یا منقضی شده: {exc.verify_message}",
        }
    except Exception as exc:
        return {
            "domain": clean_host,
            "port": port,
            "valid": False,
            "is_ip": False,
            "days_left": None,
            "expires_at": None,
            "issuer": None,
            "status": "unreachable",
            "error": f"عدم برقراری ارتباط با پورت {port}",
        }


async def check_domain_ssl(domain: str, port: int = 443, timeout: float = 4.0) -> dict[str, Any]:
    """Check a single domain's SSL certificate asynchronously."""
    return await asyncio.to_thread(_check_domain_ssl_sync, domain, port, timeout)


async def check_domains_ssl(domains: list[str], timeout: float = 4.0) -> list[dict[str, Any]]:
    """Check multiple domains concurrently with deduplication."""
    clean_domains = list(dict.fromkeys(d.strip() for d in domains if d and d.strip()))
    if not clean_domains:
        return []
    tasks = [asyncio.to_thread(_check_domain_ssl_sync, d, 443, timeout) for d in clean_domains]
    return await asyncio.gather(*tasks)


async def get_system_ssl_domains(remnawave: Any) -> list[dict[str, str]]:
    """Extract candidate SSL domains from Remnawave nodes and system settings."""
    cfg = get_settings()
    items: list[dict[str, str]] = []
    seen = set()

    def _add(host_or_url: str, label: str):
        if not host_or_url:
            return
        clean = host_or_url.strip()
        if "://" in clean:
            parsed = urllib.parse.urlparse(clean)
            clean = parsed.hostname or clean
        if ":" in clean:
            clean = clean.split(":")[0]
        clean = clean.strip().lower()
        if clean and clean not in seen:
            seen.add(clean)
            items.append({"domain": clean, "label": label})

    if cfg.WEB_APP_URL:
        _add(cfg.WEB_APP_URL, "سامانه مینی‌اپ (TMA)")
    if cfg.REMNAWAVE_BASE_URL:
        _add(cfg.REMNAWAVE_BASE_URL, "کنترل پنل Remnawave")

    if remnawave:
        try:
            nodes = await remnawave.get_nodes() or []
            for n in nodes:
                addr = str(n.get("address") or "").strip()
                name = str(n.get("name") or "نود سرور").strip()
                if addr:
                    _add(addr, f"نود: {name}")
        except Exception as exc:
            logger.warning("Could not fetch nodes for SSL domains: %s", exc)

    return items
