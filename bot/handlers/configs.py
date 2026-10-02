"""Single configs handler.

Allows users to retrieve individual configs from their subscription link.
Configs are presented in a 2-column layout within Account Management.
Selecting a config opens a dedicated detail screen showing the updated config
with a tap-to-copy code box and a back button to return to the configs list.
"""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, CopyTextButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.repositories.user_repo import UserRepository
from bot.keyboards.inline import welcome_keyboard
from bot.locales.texts import t
from bot.services.configs import fetch_subscription_configs
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient

from bot.common import SEPARATOR

logger = logging.getLogger(__name__)
router = Router(name="configs")


def _fmt_cfg_name(name: str) -> str:
    """Cap config name length to fit neatly in a 2-column inline keyboard."""
    return (name[:21] + "...") if len(name) > 24 else name


async def _get_accounts(
    remnawave: RemnawaveClient, telegram_id: int
) -> list[dict] | None:
    raw = await remnawave.get_users_by_telegram_id(telegram_id)
    if raw is None:
        return None
    seen = set()
    deduped = []
    for a in raw:
        aid = str(a.get("id"))
        if aid not in seen and str(a.get("status", "")).upper() not in ("DELETED",):
            seen.add(aid)
            deduped.append(a)
    return deduped


async def _verify_account(
    remnawave: RemnawaveClient, telegram_id: int, account_id: str | int
) -> dict | None:
    accounts = await _get_accounts(remnawave, telegram_id)
    if not accounts:
        return None
    for acc in accounts:
        if str(acc.get("id")) == str(account_id):
            return acc
    return None


def _safe_int(value: str | int | None) -> int | None:
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return None


async def _render_account_configs(
    bot: Bot,
    user,
    user_repo: UserRepository,
    account: dict,
    lang: str,
    multi: bool = False,
) -> None:
    account_id = account.get("id")
    username = escape(str(account.get("username", "—")))
    sub_url = account.get("subscriptionUrl")

    if not sub_url:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_back"), callback_data=f"acc:view:{account_id}")
        kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
        kb.adjust(1, 1)
        await render_menu(bot, user, user_repo, t(lang, "configs_empty"), kb.as_markup())
        return

    configs = await fetch_subscription_configs(sub_url)
    if not configs:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_back"), callback_data=f"acc:view:{account_id}")
        kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
        kb.adjust(1, 1)
        await render_menu(bot, user, user_repo, t(lang, "configs_empty"), kb.as_markup())
        return

    kb = InlineKeyboardBuilder()
    sizes: list[int] = []

    # 2-column layout with RTL support
    i = 0
    while i < len(configs):
        if i + 1 < len(configs):
            c_first = configs[i]
            c_second = configs[i + 1]
            if lang == "fa":
                # Persian RTL: add second item (left) then first item (right)
                kb.button(
                    text=_fmt_cfg_name(c_second["name"]),
                    callback_data=f"cfg:show:{account_id}:{i + 1}",
                )
                kb.button(
                    text=_fmt_cfg_name(c_first["name"]),
                    callback_data=f"cfg:show:{account_id}:{i}",
                )
            else:
                kb.button(
                    text=_fmt_cfg_name(c_first["name"]),
                    callback_data=f"cfg:show:{account_id}:{i}",
                )
                kb.button(
                    text=_fmt_cfg_name(c_second["name"]),
                    callback_data=f"cfg:show:{account_id}:{i + 1}",
                )
            sizes.append(2)
            i += 2
        else:
            # Single leftover item
            c_lone = configs[i]
            kb.button(
                text=_fmt_cfg_name(c_lone["name"]),
                callback_data=f"cfg:show:{account_id}:{i}",
            )
            sizes.append(1)
            i += 1

    # Navigation buttons: Back to account view | Back to main menu
    if lang == "fa":
        kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
        kb.button(text=t(lang, "btn_back"), callback_data=f"acc:view:{account_id}")
    else:
        kb.button(text=t(lang, "btn_back"), callback_data=f"acc:view:{account_id}")
        kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    sizes.append(2)

    kb.adjust(*sizes)

    text = (
        f"{t(lang, 'configs_title')}\n{SEPARATOR}\n"
        f"{t(lang, 'stats_account')} : <code>{username}</code>\n"
        f"📊 {t(lang, 'stats_total')} : <b>{len(configs)}</b>\n\n"
        f"{t(lang, 'configs_desc')}"
    )
    await render_menu(bot, user, user_repo, text, kb.as_markup())


@router.callback_query(F.data.startswith("cfg:acc:"))
async def single_configs_account_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient
):
    account_id = call.data.rsplit(":", 1)[1]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    account = await _verify_account(remnawave, user.telegram_id, account_id)
    if account is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    await _render_account_configs(bot, user, user_repo, account, lang)
    await call.answer()


@router.callback_query(F.data.startswith("cfg:show:"))
async def single_config_detail(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient
):
    parts = call.data.split(":")
    if len(parts) != 4:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    _, _, account_id, idx_s = parts
    idx = _safe_int(idx_s)
    if idx is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    account = await _verify_account(remnawave, user.telegram_id, account_id)
    if account is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    sub_url = account.get("subscriptionUrl")
    if not sub_url:
        await call.answer(t(lang, "configs_empty"), show_alert=True)
        return

    # Always fetch latest configs from subscription URL so user gets updated configs
    configs = await fetch_subscription_configs(sub_url)
    if idx < 0 or idx >= len(configs):
        await call.answer(t(lang, "configs_empty"), show_alert=True)
        return

    cfg = configs[idx]
    config_name = escape(cfg["name"])
    config_uri = escape(cfg["uri"])
    username = escape(str(account.get("username", "—")))
    proto = str(cfg.get("protocol") or "—").upper()

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_copy_config"), copy_text=CopyTextButton(text=cfg["uri"]))
    kb.button(text=t(lang, "btn_back_to_configs"), callback_data=f"cfg:acc:{account_id}")
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    kb.adjust(1, 2)

    text = (
        f"{t(lang, 'configs_view_title', name=config_name)}\n{SEPARATOR}\n"
        f"{t(lang, 'stats_account')} : <code>{username}</code>\n"
        f"🌐 {t(lang, 'cfg_protocol')} : <b>{proto}</b>\n\n"
        f"<code>{config_uri}</code>\n\n"
        f"{t(lang, 'configs_copy_hint')}"
    )

    await render_menu(bot, user, user_repo, text, kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("cfg:get:"))
async def single_config_get_legacy(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient
):
    """Legacy redirect from old get callbacks."""
    parts = call.data.split(":")
    if len(parts) == 4:
        account_id, idx_s = parts[2], parts[3]
        call.data = f"cfg:show:{account_id}:{idx_s}"
        await single_config_detail(call, bot, user_repo, remnawave)
    else:
        await call.answer()


@router.callback_query(F.data == "menu:single_configs")
async def single_configs_entry(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient
):
    """Main menu fallback redirect to account configs."""
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    accounts = await _get_accounts(remnawave, call.from_user.id)
    if accounts is None:
        await render_menu(
            bot, user, user_repo, t(lang, "stats_error"), welcome_keyboard(lang)
        )
        await call.answer()
        return

    if not accounts:
        await user_repo.set_verified(user, False)
        await render_menu(
            bot, user, user_repo, t(lang, "not_verified"), welcome_keyboard(lang)
        )
        await call.answer()
        return

    await user_repo.set_verified(user, True)

    if len(accounts) == 1:
        await _render_account_configs(bot, user, user_repo, accounts[0], lang)
        await call.answer()
        return

    # Multiple accounts -> ask user to choose account
    kb = InlineKeyboardBuilder()
    for account in accounts:
        username = escape(str(account.get("username", "—")))
        kb.button(
            text=f"👤 {username}",
            callback_data=f"cfg:acc:{account.get('id')}",
        )
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    kb.adjust(1)

    text = f"{t(lang, 'configs_title')}\n{SEPARATOR}\n{t(lang, 'configs_pick_account')}"
    await render_menu(bot, user, user_repo, text, kb.as_markup())
    await call.answer()
