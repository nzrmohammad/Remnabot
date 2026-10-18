"""Connection Guide section.

Per-platform pages with recommended client apps (download buttons),
step-by-step import instructions and the user's own subscription
link(s) for quick copying.
"""
import json
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)
router = Router(name="guide")

APP_DISPLAY_NAMES: dict[str, str] = {
    "v2rayng": "v2rayNG",
    "v2rayn": "v2rayN",
    "happ": "Happ",
    "hiddify": "Hiddify",
    "incy": "INCY",
    "onexray": "OneXray",
    "shadowrocket": "Shadowrocket",
    "streisand": "Streisand",
    "v2box": "V2Box",
    "nekoray": "NekoRay",
    "v2raya": "v2rayA",
}


def _get_platform_apps_from_json(client_apps_json: str, platform: str) -> list[tuple[str, str]]:
    if not client_apps_json:
        return []
    try:
        data = json.loads(client_apps_json) if isinstance(client_apps_json, str) else client_apps_json
        if not isinstance(data, dict):
            return []
        platform_data = data.get(platform)
        if not platform_data and platform == "windows":
            platform_data = data.get("desktop")
        if not isinstance(platform_data, dict):
            return []

        rec_app = str((data.get("recommended") or {}).get(platform, "")).lower()
        if not rec_app and platform == "windows":
            rec_app = str((data.get("recommended") or {}).get("desktop", "")).lower()

        apps: list[tuple[str, str, bool]] = []
        for app_id, cfg in platform_data.items():
            if not isinstance(cfg, dict):
                continue
            if cfg.get("enabled") is False:
                continue
            url = (
                cfg.get("download_url")
                or cfg.get("download_portable_url")
                or cfg.get("download_extra_url")
                or ""
            ).strip()
            if not url:
                continue
            name = APP_DISPLAY_NAMES.get(app_id.lower(), app_id.capitalize())
            version = str(cfg.get("version") or "").strip()
            label = f"{name} ({version})" if version else name
            is_rec = bool(rec_app and rec_app == app_id.lower())
            apps.append((label, url, is_rec))

        apps.sort(key=lambda x: 0 if x[2] else 1)
        return [(label, url) for label, url, _ in apps]
    except Exception:
        logger.exception("Failed to parse client_apps_json for guide")
        return []


# platform key -> (locale key of the button, [(app name, download url), ...])
PLATFORMS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "android": (
        "btn_platform_android",
        [
            ("INCY", "https://play.google.com/store/apps/details?id=llc.itdev.incy"),
            ("Happ", "https://play.google.com/store/apps/details?id=com.happproxy"),
            ("v2rayNG", "https://github.com/2dust/v2rayNG/releases/latest"),
            ("Hiddify", "https://github.com/hiddify/hiddify-next/releases/latest"),
            ("OneXray", "https://github.com/YuanDevTeam/OneXray/releases/latest"),
        ],
    ),
    "ios": (
        "btn_platform_ios",
        [
            ("INCY", "https://apps.apple.com/app/incy/id6756943388"),
            ("Happ", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
            ("Streisand", "https://apps.apple.com/us/app/streisand/id6450534064"),
            ("V2Box", "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690"),
            ("OneXray", "https://apps.apple.com/us/app/onexray/id6745748773"),
        ],
    ),
    "windows": (
        "btn_platform_windows",
        [
            ("INCY", "https://github.com/INCY-DEV/incy-platforms/releases/latest"),
            ("Happ", "https://github.com/Happ-proxy/happ-desktop/releases/latest"),
            ("v2rayN", "https://github.com/2dust/v2rayN/releases/latest"),
            ("Hiddify", "https://github.com/hiddify/hiddify-next/releases/latest"),
            ("OneXray", "https://github.com/YuanDevTeam/OneXray/releases/latest"),
        ],
    ),
    "macos": (
        "btn_platform_macos",
        [
            ("INCY", "https://apps.apple.com/app/incy/id6756943388"),
            ("Happ", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
            ("Hiddify", "https://github.com/hiddify/hiddify-next/releases/latest"),
            ("V2Box", "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690"),
            ("OneXray", "https://apps.apple.com/us/app/onexray/id6745748773"),
        ],
    ),
    "linux": (
        "btn_platform_linux",
        [
            ("Hiddify", "https://github.com/hiddify/hiddify-next/releases/latest"),
            ("v2rayN", "https://github.com/2dust/v2rayN/releases/latest"),
            ("OneXray", "https://apps.apple.com/us/app/onexray/id6745748773"),
        ],
    ),
}


@router.callback_query(F.data == "menu:guide")
async def guide_entry(call: CallbackQuery, bot: Bot, user_repo: UserRepository):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    kb = InlineKeyboardBuilder()
    for key, (btn_key, _apps) in PLATFORMS.items():
        kb.button(text=t(lang, btn_key), callback_data=f"guide:{key}")
    kb.button(text=t(lang, "btn_back"), callback_data="nav:main_menu")
    kb.adjust(2, 2, 1, 1)

    text = f"{t(lang, 'guide_title')}\n{SEPARATOR}\n{t(lang, 'guide_pick')}"
    await render_menu(bot, user, user_repo, text, kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("guide:"))
async def guide_platform(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    remnawave: RemnawaveClient,
    session: AsyncSession | None = None,
):
    platform = call.data.split(":", 1)[1]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    entry = PLATFORMS.get(platform)
    if entry is None:
        await call.answer()
        return
    btn_key, default_apps = entry

    apps = default_apps
    if session is not None:
        try:
            store_settings = await get_store_settings(session)
            if store_settings.client_apps_json:
                dynamic_apps = _get_platform_apps_from_json(store_settings.client_apps_json, platform)
                if dynamic_apps:
                    apps = dynamic_apps
        except Exception:
            logger.exception("Failed to load dynamic apps for guide:%s", platform)

    lines = [
        f"{t(lang, 'guide_title')} — {t(lang, btn_key)}",
        SEPARATOR,
        t(lang, "guide_steps"),
    ]

    # the user's own subscription link(s), ready to copy
    accounts = await remnawave.get_users_by_telegram_id(call.from_user.id) or []
    with_url = [a for a in accounts if a.get("subscriptionUrl")]
    if with_url:
        lines += ["", t(lang, "guide_your_link")]
        for account in with_url:
            prefix = ""
            if len(with_url) > 1:
                prefix = f"👤 {escape(str(account.get('username', '—')))} :\n"
            lines.append(f"{prefix}<code>{escape(account['subscriptionUrl'])}</code>")

    kb = InlineKeyboardBuilder()
    for name, url in apps:
        kb.button(text=f"⬇️ {name}", url=url)
    kb.button(text=t(lang, "btn_back"), callback_data="menu:guide")
    sizes = [2] * (len(apps) // 2) + ([1] if len(apps) % 2 else [])
    if sizes:
        kb.adjust(*sizes, 1)
    else:
        kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()
