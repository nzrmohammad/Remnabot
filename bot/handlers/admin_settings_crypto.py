"""Admin Crypto Payment and Exchange Rate Settings."""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, is_admin, resolve_op
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.menu import render_menu

logger = logging.getLogger(__name__)
router = Router(name="admin_settings_crypto")

_is_admin = is_admin


async def _render_crypto_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    store_fn = resolve_op("get_store_settings", get_store_settings)
    render_menu_fn = resolve_op("render_menu", render_menu)

    lang = user.language or "fa"
    store = await store_fn(session)
    kb = InlineKeyboardBuilder()

    status_badge = "✅" if store.crypto_enabled else "❌"
    rate_str = f"{store.ton_rate_toman:,} تومان" if store.ton_rate_toman > 0 else "— (تنظیم‌نشده)"
    wallet_str = store.ton_wallet_address or "— (تنظیم‌نشده)"

    lossless_stars = max(100, round(store.usdt_rate_toman * 0.013))
    stars_rate_str = f"{store.stars_rate_toman:,} تومان" if store.stars_rate_toman > 0 else f"{lossless_stars:,} تومان (محاسبه خودکار)"

    if lang == "fa":
        kb.button(
            text=f"⚡️ وضعیت درگاه {status_badge}",
            callback_data="adm:settings:toggle:crypto_enabled",
        )
        kb.button(text="💰 نرخ تبدیل تون", callback_data="adm:set:ton_rate_toman")
        kb.button(text="💵 نرخ مبنای تتر", callback_data="adm:set:usdt_rate_toman")
        kb.button(text="⭐️ نرخ هر استارز", callback_data="adm:set:stars_rate_toman")
        kb.button(text="📬 آدرس والت", callback_data="adm:set:ton_wallet_address")
        kb.button(text="💎 استعلام نرخ تون", callback_data="adm:crypto:rate:ton")
        kb.button(text="💵 استعلام نرخ تتر", callback_data="adm:crypto:rate:usdt")
    else:
        kb.button(
            text=f"⚡️ Status {status_badge}",
            callback_data="adm:settings:toggle:crypto_enabled",
        )
        kb.button(text="💰 TON Rate", callback_data="adm:set:ton_rate_toman")
        kb.button(text="💵 USDT Rate", callback_data="adm:set:usdt_rate_toman")
        kb.button(text="⭐️ Stars Rate", callback_data="adm:set:stars_rate_toman")
        kb.button(text="📬 Wallet Address", callback_data="adm:set:ton_wallet_address")
        kb.button(text="💎 Check TON Price", callback_data="adm:crypto:rate:ton")
        kb.button(text="💵 Check USDT Price", callback_data="adm:crypto:rate:usdt")

    kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    kb.adjust(1, 3, 1, 2, 1)

    lines = [
        "💎 <b>تنظیمات پرداخت کریپتو</b>\n" + SEPARATOR,
        f"⚡️ وضعیت درگاه : <b>{status_badge}</b>",
        f"📬 آدرس والت مقصد : <code>{escape(wallet_str)}</code>",
        f"💰 نرخ تبدیل (۱ تون) : <b>{rate_str}</b>",
        f"💵 نرخ مبنای تتر : <b>{store.usdt_rate_toman:,} تومان</b>",
        f"⭐️ نرخ هر استارز : <b>{stars_rate_str}</b> (فرمول بدون ضرر: <b>{lossless_stars:,} ت</b>)\n",
        "💡 ربات روزانه ۴ بار (ساعت‌های ۱۰:۰۰، ۱۴:۰۰، ۱۸:۰۰ و ۲۲:۰۰) قیمت لحظه‌ای را در تاپیک کریپتو ارسال می‌کند تا با یک کلیک بتوانید نرخ فروشگاه را آپدیت فرمایید.",
    ] if lang == "fa" else [
        "💎 <b>Crypto & Currency Settings</b>\n" + SEPARATOR,
        f"⚡️ Status : <b>{status_badge}</b>",
        f"📬 Wallet : <code>{escape(wallet_str)}</code>",
        f"💰 Rate : <b>{rate_str}</b>",
        f"💵 USDT Rate : <b>{store.usdt_rate_toman:,} Toman</b>",
        f"⭐️ Stars Rate : <b>{stars_rate_str}</b>",
    ]

    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "adm:settings:crypto")
async def crypto_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_crypto_fn = resolve_op("_render_crypto_settings", _render_crypto_settings)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_crypto_fn(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:settings:toggle:crypto_enabled")
async def toggle_crypto_enabled(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    store_fn = resolve_op("get_store_settings", get_store_settings)
    app_setting_repo_cls = resolve_op("AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = resolve_op("AdminLogRepository", AdminLogRepository)
    render_crypto_fn = resolve_op("_render_crypto_settings", _render_crypto_settings)

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    store = await store_fn(session)
    new_val = not store.crypto_enabled
    await app_setting_repo_cls(session).set("crypto_enabled", "1" if new_val else "0")
    await admin_log_repo_cls(session).log(
        call.from_user.id, "setting", detail=f"crypto_enabled={'1' if new_val else '0'}"
    )
    await render_crypto_fn(bot, user, user_repo, session)
    await call.answer("✅ وضعیت پرداخت کریپتو تغییر یافت.")


@router.callback_query(F.data.in_({"adm:crypto:rate:ton", "adm:crypto:nobitex_now"}))
async def crypto_ton_rate_now(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    store_fn = resolve_op("get_store_settings", get_store_settings)
    render_menu_fn = resolve_op("render_menu", render_menu)

    from bot.services.crypto.nobitex import fetch_all_exchange_prices, format_ton_rate_alert
    store = await store_fn(session)
    market_data = await fetch_all_exchange_prices(usdt_rate=store.usdt_rate_toman)
    best_ton, _ = market_data.get("best_ton", (None, ""))
    if best_ton is None and not market_data.get("ton"):
        await call.answer(
            "❌ خطا در استعلام قیمت تون از صرافی‌ها.",
            show_alert=True,
        )
        return

    text, kb = format_ton_rate_alert(
        market_data=market_data,
        current_ton_rate=store.ton_rate_toman,
    )
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_menu_fn(bot, user, user_repo, text, kb)
    await call.answer("✅ استعلام قیمت لحظه‌ای تون انجام شد.")


crypto_nobitex_now = crypto_ton_rate_now


@router.callback_query(F.data == "adm:crypto:rate:usdt")
async def crypto_usdt_rate_now(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    store_fn = resolve_op("get_store_settings", get_store_settings)
    render_menu_fn = resolve_op("render_menu", render_menu)

    from bot.services.crypto.nobitex import fetch_all_exchange_prices, format_usdt_rate_alert
    store = await store_fn(session)
    market_data = await fetch_all_exchange_prices(usdt_rate=store.usdt_rate_toman)
    best_usdt, _ = market_data.get("best_usdt", (None, ""))
    if best_usdt is None and not market_data.get("usdt"):
        await call.answer(
            "❌ خطا در استعلام قیمت تتر از صرافی‌ها.",
            show_alert=True,
        )
        return

    text, kb = format_usdt_rate_alert(
        market_data=market_data,
        current_usdt_rate=store.usdt_rate_toman,
    )
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_menu_fn(bot, user, user_repo, text, kb)
    await call.answer("✅ استعلام قیمت لحظه‌ای تتر انجام شد.")


@router.callback_query(F.data.startswith("adm:rate:apply:"))
async def apply_nobitex_rate(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    app_setting_repo_cls = resolve_op("AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = resolve_op("AdminLogRepository", AdminLogRepository)

    try:
        parts = call.data.split(":")
        if len(parts) >= 5 and parts[3] in ("ton", "usdt", "stars"):
            kind = parts[3]
            price = int(parts[4])
        else:
            kind = "ton"
            price = int(parts[3])
    except (ValueError, IndexError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    if kind == "ton":
        setting_key = "ton_rate_toman"
        kind_title = "نرخ تون"
    elif kind == "stars":
        setting_key = "stars_rate_toman"
        kind_title = "نرخ استارز تلگرام"
    else:
        setting_key = "usdt_rate_toman"
        kind_title = "نرخ مبنای تتر"

    await app_setting_repo_cls(session).set(setting_key, str(price))
    await admin_log_repo_cls(session).log(
        call.from_user.id, "setting", detail=f"{setting_key}={price}"
    )
    await session.commit()

    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 بازگشت به تنظیمات کریپتو", callback_data="adm:settings:crypto")
    kb.button(text="⚙️ تنظیمات فروشگاه", callback_data="adm:settings")
    kb.adjust(1)

    await call.answer(f"✅ {kind_title} فروشگاه روی {price:,} تومان تنظیم شد.", show_alert=True)
    try:
        await call.message.edit_text(
            f"{call.message.html_text}\n\n✅ <b>{kind_title} فروشگاه با موفقیت روی {price:,} تومان تنظیم شد.</b>",
            reply_markup=kb.as_markup(),
        )
    except Exception:
        pass
