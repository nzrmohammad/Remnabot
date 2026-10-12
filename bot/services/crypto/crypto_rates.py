"""Crypto alert message and keyboard formatters."""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def format_rate_alert(
    nobitex_price: int, current_rate: int, hour_str: str = "", source_name: str = "نوبیتکس"
) -> tuple[str, InlineKeyboardMarkup]:
    """Format single-source rate notification text and keyboard with proper LTR signs."""
    diff = nobitex_price - current_rate

    if current_rate > 0:
        percent = (diff / current_rate) * 100.0
    else:
        percent = 0.0

    if diff > 0:
        diff_str = f"{diff:,}+ تومان"
        percent_str = f"(%{percent:.1f}+)"
    elif diff < 0:
        diff_str = f"{abs(diff):,}- تومان"
        percent_str = f"(%{abs(percent):.1f}-)"
    else:
        diff_str = "0 تومان"
        percent_str = "(0%)"

    curr_rate_str = f"{current_rate:,} تومان" if current_rate > 0 else "— (تنظیم‌نشده)"

    time_header = f" — ساعت {hour_str}" if hour_str else ""
    src_title = source_name or "نوبیتکس"
    text = (
        f"💎 <b>استعلام نرخ تون ({src_title}){time_header}</b>\n"
        f"──────────────────\n"
        f"📊 قیمت لحظه‌ای {src_title} : <b>{nobitex_price:,}</b> تومان\n"
        f"⚙️ نرخ فعلی در فروشگاه : <b>{curr_rate_str}</b>\n"
        f"📈 اختلاف : <b>{diff_str}</b> <b>{percent_str}</b>\n\n"
        f"💡 برای به‌روزرسانی نرخ در فروشگاه، دکمه زیر را لمس کنید:"
    )

    kb = InlineKeyboardBuilder()
    kb.button(
        text=f"🔄 اعمال قیمت {src_title} ({nobitex_price:,} تومان)",
        callback_data=f"adm:rate:apply:{nobitex_price}",
    )
    kb.button(
        text="✏️ تنظیم نرخ دلخواه",
        callback_data="adm:set:ton_rate_toman",
    )
    kb.button(
        text="🔙 بازگشت",
        callback_data="adm:settings:crypto",
    )
    kb.adjust(1)

    return text, kb.as_markup()


def format_multi_rate_alert(
    market_data: dict,
    current_ton_rate: int,
    current_usdt_rate: int,
    hour_str: str = "",
) -> tuple[str, InlineKeyboardMarkup]:
    """Format comprehensive rate notification showing Nobitex, Bitpin, Wallex, and USDT rates."""
    ton_prices = market_data.get("ton", {})
    usdt_prices = market_data.get("usdt", {})
    binance_usd = market_data.get("binance_usd")

    best_ton_p, best_ton_src = market_data.get("best_ton", (None, ""))
    ref_ton_price = best_ton_p or current_ton_rate

    diff_ton = ref_ton_price - current_ton_rate
    if current_ton_rate > 0:
        percent = (diff_ton / current_ton_rate) * 100.0
    else:
        percent = 0.0

    if diff_ton > 0:
        diff_str = f"{diff_ton:,}+ تومان"
        percent_str = f"(%{percent:.1f}+)"
    elif diff_ton < 0:
        diff_str = f"{abs(diff_ton):,}- تومان"
        percent_str = f"(%{abs(percent):.1f}-)"
    else:
        diff_str = "0 تومان"
        percent_str = "(0%)"

    curr_ton_str = f"{current_ton_rate:,} تومان" if current_ton_rate > 0 else "— (تنظیم‌نشده)"
    curr_usdt_str = f"{current_usdt_rate:,} تومان" if current_usdt_rate > 0 else "—"

    time_header = f" — ساعت {hour_str}" if hour_str else ""

    lines = [
        f"💎 <b>استعلام نرخ لحظه‌ای صرافی‌ها{time_header}</b>",
        "──────────────────",
        "📊 <b>قیمت لحظه‌ای تون (TON):</b>",
    ]

    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = ton_prices.get(name)
        val_str = f"<b>{p:,}</b> تومان" if p else "<i>عدم دسترسی</i>"
        lines.append(f"   🔹 {name} : {val_str}")

    if binance_usd:
        lines.append(f"   🌐 بایننس جهانی : <b>${binance_usd:.2f}</b>")

    lines.append("")
    lines.append("💵 <b>قیمت لحظه‌ای تتر (USDT / دلار):</b>")
    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = usdt_prices.get(name)
        val_str = f"<b>{p:,}</b> تومان" if p else "<i>عدم دسترسی</i>"
        lines.append(f"   🔹 {name} : {val_str}")

    lines.append("")
    lines.append("⚙️ <b>وضعیت فعلی در فروشگاه:</b>")
    lines.append(f"   💎 نرخ فعلی تون : <b>{curr_ton_str}</b>")
    if current_ton_rate > 0 and ref_ton_price:
        lines.append(f"   📈 اختلاف تون : <b>{diff_str}</b> <b>{percent_str}</b>")
    lines.append(f"   💵 نرخ مبنای تتر : <b>{curr_usdt_str}</b>")
    lines.append("")
    lines.append("💡 برای به‌روزرسانی نرخ در فروشگاه، دکمه مورد نظر را لمس فرمایید:")

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()

    ton_btns_count = 0
    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = ton_prices.get(name)
        if p:
            kb.button(
                text=f"🔄 اعمال تون {name} ({p:,} تومان)",
                callback_data=f"adm:rate:apply:ton:{p}",
            )
            ton_btns_count += 1

    usdt_btns_count = 0
    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = usdt_prices.get(name)
        if p:
            kb.button(
                text=f"💵 اعمال تتر {name} ({p:,} تومان)",
                callback_data=f"adm:rate:apply:usdt:{p}",
            )
            usdt_btns_count += 1

    kb.button(text="✏️ نرخ دلخواه تون", callback_data="adm:set:ton_rate_toman")
    kb.button(text="✏️ نرخ دلخواه تتر", callback_data="adm:set:usdt_rate_toman")
    kb.button(text="🔙 بازگشت", callback_data="adm:settings:crypto")

    adjust_spec = [1] * ton_btns_count + [1] * usdt_btns_count + [2, 1]
    kb.adjust(*adjust_spec)

    return text, kb.as_markup()


def format_ton_rate_alert(
    market_data: dict,
    current_ton_rate: int,
    hour_str: str = "",
) -> tuple[str, InlineKeyboardMarkup]:
    """Format TON price notification showing Nobitex, Bitpin, Wallex, and Binance."""
    ton_prices = market_data.get("ton", {})
    binance_usd = market_data.get("binance_usd")

    best_ton_p, best_ton_src = market_data.get("best_ton", (None, ""))
    ref_ton_price = best_ton_p or current_ton_rate

    diff_ton = ref_ton_price - current_ton_rate
    if current_ton_rate > 0:
        percent = (diff_ton / current_ton_rate) * 100.0
    else:
        percent = 0.0

    if diff_ton > 0:
        diff_str = f"{diff_ton:,}+ تومان"
        percent_str = f"(%{percent:.1f}+)"
    elif diff_ton < 0:
        diff_str = f"{abs(diff_ton):,}- تومان"
        percent_str = f"(%{abs(percent):.1f}-)"
    else:
        diff_str = "0 تومان"
        percent_str = "(0%)"

    curr_ton_str = f"{current_ton_rate:,} تومان" if current_ton_rate > 0 else "— (تنظیم‌نشده)"
    time_header = f" — ساعت {hour_str}" if hour_str else ""

    lines = [
        f"💎 <b>استعلام نرخ لحظه‌ای تون (TON){time_header}</b>",
        "──────────────────",
        "📊 <b>قیمت لحظه‌ای تون در صرافی‌ها:</b>",
    ]

    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = ton_prices.get(name)
        val_str = f"<b>{p:,}</b> تومان" if p else "<i>عدم دسترسی</i>"
        lines.append(f"   🔹 {name} : {val_str}")

    if binance_usd:
        lines.append(f"   🌐 بایننس جهانی : <b>${binance_usd:.2f}</b>")

    lines.append("")
    lines.append("⚙️ <b>وضعیت فعلی در فروشگاه:</b>")
    lines.append(f"   💎 نرخ فعلی تون : <b>{curr_ton_str}</b>")
    if current_ton_rate > 0 and ref_ton_price:
        lines.append(f"   📈 اختلاف تون : <b>{diff_str}</b> <b>{percent_str}</b>")
    lines.append("")
    lines.append("💡 برای به‌روزرسانی نرخ در فروشگاه، دکمه مورد نظر را لمس فرمایید:")

    text = "\n".join(lines)
    kb = InlineKeyboardBuilder()

    ton_btns_count = 0
    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = ton_prices.get(name)
        if p:
            kb.button(
                text=f"🔄 اعمال تون {name} ({p:,} تومان)",
                callback_data=f"adm:rate:apply:ton:{p}",
            )
            ton_btns_count += 1

    kb.adjust(1)

    return text, kb.as_markup()


def format_usdt_rate_alert(
    market_data: dict,
    current_usdt_rate: int,
    hour_str: str = "",
) -> tuple[str, InlineKeyboardMarkup]:
    """Format USDT price notification showing Nobitex, Bitpin, Wallex."""
    usdt_prices = market_data.get("usdt", {})

    best_usdt_p, best_usdt_src = market_data.get("best_usdt", (None, ""))
    ref_usdt_price = best_usdt_p or current_usdt_rate

    diff_usdt = ref_usdt_price - current_usdt_rate
    if current_usdt_rate > 0:
        percent = (diff_usdt / current_usdt_rate) * 100.0
    else:
        percent = 0.0

    if diff_usdt > 0:
        diff_str = f"{diff_usdt:,}+ تومان"
        percent_str = f"(%{percent:.1f}+)"
    elif diff_usdt < 0:
        diff_str = f"{abs(diff_usdt):,}- تومان"
        percent_str = f"(%{abs(percent):.1f}-)"
    else:
        diff_str = "0 تومان"
        percent_str = "(0%)"

    curr_usdt_str = f"{current_usdt_rate:,} تومان" if current_usdt_rate > 0 else "—"
    time_header = f" — ساعت {hour_str}" if hour_str else ""

    lines = [
        f"💵 <b>استعلام نرخ لحظه‌ای تتر (USDT / دلار){time_header}</b>",
        "──────────────────",
        "📊 <b>قیمت لحظه‌ای تتر در صرافی‌ها:</b>",
    ]

    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = usdt_prices.get(name)
        val_str = f"<b>{p:,}</b> تومان" if p else "<i>عدم دسترسی</i>"
        lines.append(f"   🔹 {name} : {val_str}")

    lines.append("")
    lines.append("⚙️ <b>وضعیت فعلی در فروشگاه:</b>")
    lines.append(f"   💵 نرخ مبنای تتر : <b>{curr_usdt_str}</b>")
    if current_usdt_rate > 0 and ref_usdt_price:
        lines.append(f"   📈 اختلاف تتر : <b>{diff_str}</b> <b>{percent_str}</b>")
    lossless_stars = round(ref_usdt_price * 0.013)
    fragment_stars = round(ref_usdt_price * 0.015)
    lines.append(f"   ⭐️ نرخ بدون ضرر استارز (۰.۰۱۳$) : <b>{lossless_stars:,} تومان</b>")
    lines.append(f"   🏷 نرخ فرگمنت استارز (۰.۰۱۵$) : <b>{fragment_stars:,} تومان</b>")
    lines.append("")
    lines.append("💡 برای به‌روزرسانی نرخ در فروشگاه، دکمه مورد نظر را لمس فرمایید:")

    text = "\n".join(lines)
    kb = InlineKeyboardBuilder()

    usdt_btns_count = 0
    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = usdt_prices.get(name)
        if p:
            kb.button(
                text=f"💵 اعمال تتر {name} ({p:,} تومان)",
                callback_data=f"adm:rate:apply:usdt:{p}",
            )
            usdt_btns_count += 1

    if best_usdt_p:
        lossless_stars_best = round(best_usdt_p * 0.013)
        kb.button(
            text=f"⭐️ اعمال استارز بدون ضرر ({lossless_stars_best:,} تومان)",
            callback_data=f"adm:rate:apply:stars:{lossless_stars_best}",
        )

    kb.adjust(1)

    return text, kb.as_markup()
