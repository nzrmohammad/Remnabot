"""Connection Guide section.

Per-platform pages with recommended client apps (download buttons),
step-by-step import instructions and the user's own subscription
link(s) for quick copying.
"""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)
router = Router(name="guide")

SEPARATOR = "─" * 18

# platform key -> (locale key of the button, [(app name, download url), ...])
PLATFORMS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "android": (
        "btn_platform_android",
        [
            ("Happ", "https://play.google.com/store/apps/details?id=com.happproxy"),
            ("v2rayNG", "https://github.com/2dust/v2rayNG/releases/latest"),
            ("Hiddify", "https://github.com/hiddify/hiddify-next/releases/latest"),
        ],
    ),
    "ios": (
        "btn_platform_ios",
        [
            ("Happ", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
            ("Streisand", "https://apps.apple.com/us/app/streisand/id6450534064"),
            ("V2Box", "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690"),
        ],
    ),
    "windows": (
        "btn_platform_windows",
        [
            ("Happ", "https://github.com/Happ-proxy/happ-desktop/releases/latest"),
            ("v2rayN", "https://github.com/2dust/v2rayN/releases/latest"),
            ("Hiddify", "https://github.com/hiddify/hiddify-next/releases/latest"),
        ],
    ),
    "macos": (
        "btn_platform_macos",
        [
            ("Happ", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
            ("Hiddify", "https://github.com/hiddify/hiddify-next/releases/latest"),
            ("V2Box", "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690"),
        ],
    ),
    "linux": (
        "btn_platform_linux",
        [
            ("Hiddify", "https://github.com/hiddify/hiddify-next/releases/latest"),
            ("v2rayN", "https://github.com/2dust/v2rayN/releases/latest"),
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
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    kb.adjust(2, 2, 1, 1)

    text = f"{t(lang, 'guide_title')}\n{SEPARATOR}\n{t(lang, 'guide_pick')}"
    await render_menu(bot, user, user_repo, text, kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("guide:"))
async def guide_platform(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient
):
    platform = call.data.split(":", 1)[1]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    entry = PLATFORMS.get(platform)
    if entry is None:
        await call.answer()
        return
    btn_key, apps = entry

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
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    sizes = [2] * (len(apps) // 2) + ([1] if len(apps) % 2 else [])
    kb.adjust(*sizes, 1, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()
