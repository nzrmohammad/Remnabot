"""Telegram Inline Mode handler.

Provides rich interactive inline query results:
1. User's active subscription card(s) with live traffic and expiration
2. Referral invitation card with 1-click invite link
3. Live network server status and online locations (100% real data, zero fake fallbacks)
4. Free trial invitation card
"""
import logging
from html import escape

from aiogram import Bot, Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common.links import ref_link
from bot.config import get_settings
from bot.db.repositories.user_repo import UserRepository
from bot.services.app_settings import get_store_settings
from bot.services.formatting import country_flag, country_name, now_tz, parse_iso
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)
router = Router(name="inline")


def _format_traffic_compact(used: int, limit: int) -> str:
    if limit <= 0:
        return "نامحدود"
    remaining = max(0, limit - used)
    gb = remaining / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.1f} GB" if round(gb, 1) != int(gb) else f"{int(gb)} GB"
    mb = remaining / (1024 ** 2)
    return f"{mb:.0f} MB" if mb >= 1 else "0 MB"


def _format_days_left(expire_at_raw: str | None, tz_name: str) -> str:
    expire_at = parse_iso(expire_at_raw)
    if expire_at is None:
        return "بدون انقضا"
    now = now_tz(tz_name)
    delta_days = (expire_at - now).days
    if delta_days > 0:
        return f"{delta_days} روز"
    if delta_days == 0:
        return "امروز"
    return "منقضی شده"


@router.inline_query()
async def inline_query_handler(
    query: InlineQuery,
    bot: Bot,
    session: AsyncSession,
    user_repo: UserRepository,
    remnawave: RemnawaveClient,
) -> None:
    user_id = query.from_user.id
    settings = get_settings()
    tz_name = getattr(settings, "TIMEZONE", "Asia/Tehran")

    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username or "bot"
    except Exception:
        bot_username = "bot"

    user = await user_repo.get_by_telegram_id(user_id)
    if user and user.is_banned:
        await query.answer(results=[], cache_time=30, is_personal=True)
        return

    store_settings = await get_store_settings(session)
    invite_link = ref_link(bot_username, user_id)
    search_text = (query.query or "").strip().lower()

    results: list[InlineQueryResultArticle] = []

    # 1. User Accounts / Subscriptions
    accounts = []
    if remnawave:
        try:
            raw_accounts = await remnawave.get_users_by_telegram_id(user_id) or []
            seen = set()
            for a in raw_accounts:
                aid = str(a.get("id"))
                if aid not in seen and str(a.get("status", "")).upper() not in ("DELETED",):
                    seen.add(aid)
                    accounts.append(a)
        except Exception as exc:
            logger.debug("Inline: failed fetching panel accounts for %s: %s", user_id, exc)

    if accounts:
        for acc in accounts:
            acc_id = str(acc.get("id", ""))
            uname = escape(str(acc.get("username", "—")))
            limit = int(acc.get("trafficLimitBytes") or 0)
            traffic = acc.get("userTraffic") or {}
            used = int(traffic.get("usedTrafficBytes") or acc.get("usedTrafficBytes") or 0)
            status_raw = str(acc.get("status", "ACTIVE")).upper()
            status_fa = {
                "ACTIVE": "فعال ✅",
                "DISABLED": "غیرفعال ⏸",
                "LIMITED": "اتمام حجم ⚠️",
                "EXPIRED": "منقضی شده ❌",
            }.get(status_raw, "فعال ✅")

            traffic_str = _format_traffic_compact(used, limit)
            days_str = _format_days_left(acc.get("expireAt"), tz_name)
            sub_url = acc.get("subscriptionUrl") or ""

            msg_lines = [
                f"⚡ <b>وضعیت اشتراک {uname}</b>",
                "──────────────────",
                f"📊 <b>حجم باقی‌مانده:</b> <code>{traffic_str}</code>",
                f"⏳ <b>اعتبار باقی‌مانده:</b> <code>{days_str}</code>",
                f"📶 <b>وضعیت سرویس:</b> <code>{status_fa}</code>",
                "──────────────────",
                f"🚀 <i>ارائه شده توسط @{bot_username}</i>",
            ]

            buttons = []
            if sub_url:
                buttons.append([InlineKeyboardButton(text="🔗 کپی لینک اتصال", url=sub_url)])
            buttons.append([InlineKeyboardButton(text="📱 ورود به مینی‌اپ", url=f"https://t.me/{bot_username}?start=app")])

            results.append(
                InlineQueryResultArticle(
                    id=f"sub_{acc_id}",
                    title=f"⚡ اشتراک من: {acc.get('username')}",
                    description=f"باقی‌مانده: {traffic_str} | اعتبار: {days_str} | وضعیت: {status_fa}",
                    input_message_content=InputTextMessageContent(
                        message_text="\n".join(msg_lines),
                        parse_mode="HTML",
                    ),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                )
            )
    else:
        # Prompt to buy subscription if no active accounts
        results.append(
            InlineQueryResultArticle(
                id="sub_buy",
                title="🛍 خرید و فعال‌سازی اشتراک",
                description="مشاهده پلن‌ها و خرید آنی اشتراک پرسرعت و پایدار",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        "🚀 <b>خرید و فعال‌سازی آنی اشتراک</b>\n"
                        "──────────────────\n"
                        "⚡️ سرورهای قدرتمند، آی‌پی ثابت و پشتیبانی از تمامی اپراتورها\n"
                        "جهت مشاهده تعرفه‌ها و خرید اشتراک، روی دکمه زیر کلیک کنید:"
                    ),
                    parse_mode="HTML",
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🛍 مشاهده تعرفه‌ها و خرید", url=f"https://t.me/{bot_username}?start=shop")]
                    ]
                ),
            )
        )

    # 2. Referral Invite Card
    reward_gb = getattr(store_settings, "referral_reward_gb", 0)
    reward_text = f" و دریافت {reward_gb} گیگابایت هدیه" if reward_gb > 0 else ""
    ref_msg = (
        f"🚀 <b>تجربه اینترنت آزاد، امن و پرسرعت بدون قطعی!</b>\n"
        f"──────────────────\n"
        f"🎁 با عضویت از طریق لینک زیر{reward_text}، اشتراک با کیفیت دریافت کنید:\n"
        f"🔗 <code>{invite_link}</code>\n"
        f"──────────────────\n"
        f"🛡 تونل اختصاصی، پینگ پایین و بدون افت سرعت"
    )
    results.append(
        InlineQueryResultArticle(
            id=f"ref_{user_id}",
            title="🎁 دعوت از دوستان (دریافت هدیه و حجم)",
            description="اشتراک‌گذاری لینک دعوت اختصاصی خود با دوستان در گروه‌ها و چت‌ها",
            input_message_content=InputTextMessageContent(
                message_text=ref_msg,
                parse_mode="HTML",
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🎁 دریافت هدیه و شروع", url=invite_link)]
                ]
            ),
        )
    )

    # 3. Live Server Status Card (Zero fake data)
    nodes = []
    if remnawave:
        try:
            nodes = await remnawave.get_nodes() or []
        except Exception as exc:
            logger.debug("Inline: failed fetching nodes: %s", exc)

    if nodes:
        # Group by country code
        country_nodes: dict[str, int] = {}
        for n in nodes:
            if isinstance(n, dict):
                cc = str(n.get("countryCode") or n.get("country_code") or "").strip().upper()
                if cc:
                    country_nodes[cc] = country_nodes.get(cc, 0) + 1

        if country_nodes:
            loc_lines = []
            for cc, count in sorted(country_nodes.items(), key=lambda x: x[1], reverse=True):
                flag = country_flag(cc)
                c_fa = country_name(cc) or cc
                loc_lines.append(f"{flag} <b>{c_fa}:</b> <code>{count} سرور آنلاین</code>")

            server_msg = (
                "🌐 <b>وضعیت آنلاین سرورها و لوکیشن‌های فعال</b>\n"
                "──────────────────\n"
                + "\n".join(loc_lines)
                + "\n──────────────────\n"
                "✅ کلیه سرورها مجهز به پروتکل‌های ضد فیلتر و رمزنگاری پیشرفته هستند."
            )
            results.append(
                InlineQueryResultArticle(
                    id="server_status",
                    title="🌐 وضعیت سرورها و لوکیشن‌های فعال",
                    description=f"نمایش زنده {len(country_nodes)} لوکیشن متصل و آنلاین در شبکه",
                    input_message_content=InputTextMessageContent(
                        message_text=server_msg,
                        parse_mode="HTML",
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="🚀 خرید و اتصال به سرورها", url=f"https://t.me/{bot_username}?start=shop")]
                        ]
                    ),
                )
            )

    # 4. Free Trial Card (if trial is enabled in store settings)
    trial_enabled = bool(getattr(store_settings, "trial_enabled", True))
    if trial_enabled:
        trial_msg = (
            "⚡️ <b>تست رایگان کیفیت و سرعت</b>\n"
            "──────────────────\n"
            "جهت دریافت اکانت تست رایگان و بررسی کیفیت، سرعت و پینگ سرورها، روی دکمه زیر کلیک کنید:\n"
            "──────────────────\n"
            "⏱ فعال‌سازی آنی و خودکار"
        )
        results.append(
            InlineQueryResultArticle(
                id="trial_invite",
                title="⚡ دریافت اشتراک تست رایگان",
                description="ارسال دعوت تست رایگان برای سنجش پایداری و سرعت سرورها",
                input_message_content=InputTextMessageContent(
                    message_text=trial_msg,
                    parse_mode="HTML",
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="⚡️ شروع تست رایگان", url=f"https://t.me/{bot_username}?start=trial")]
                    ]
                ),
            )
        )

    # Keyword search filtering if user typed words after @bot
    if search_text:
        filtered = []
        for r in results:
            text_haystack = f"{r.id} {r.title} {r.description}".lower()
            if search_text in text_haystack:
                filtered.append(r)
            elif any(w in text_haystack for w in search_text.split()):
                filtered.append(r)
        if filtered:
            results = filtered

    await query.answer(
        results=results,
        cache_time=15,
        is_personal=True,
    )
