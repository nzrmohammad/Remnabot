from sqlalchemy.exc import IntegrityError

from bot.web.user_common import db_session, require_user

"""TMA User Wallet and Top-up API endpoints."""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from html import escape

# InlineKeyboardBuilder imported lazily when sending admin alerts
from aiohttp import web

from bot.common import admin_thread_kwargs
from bot.db.repositories.crypto_repo import CryptoRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.app_settings import get_store_settings
from bot.services.crypto.nobitex import resolve_stars_rate
from bot.services.crypto.ton import fetch_ton_transactions
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def get_user_topup_info(request: web.Request) -> web.Response:
    """Return payment methods configuration (card and crypto settings)."""
    user_auth, err = require_user(request)
    if err:
        return err

    user_id = user_auth["id"]
    cache = request.app.get("cache")
    cache_key = f"tma:user:{user_id}:topup_info"
    if cache and hasattr(cache, "get"):
        cached_data = await cache.get(cache_key)
        if cached_data is not None:
            return web.json_response(cached_data)

    from bot.db.repositories.user_repo import UserRepository
    from bot.services.app_settings import get_store_settings

    async with db_session(request) as session:
        store = await get_store_settings(session)
        is_phone_verified = False
        if hasattr(session, "execute"):
            try:
                user_repo = UserRepository(session)
                db_user = await user_repo.get_by_telegram_id(user_auth["id"])
                is_phone_verified = bool(db_user and getattr(db_user, "phone_number", None) and db_user.phone_number.strip())
            except Exception:
                is_phone_verified = False
        require_phone = getattr(store, "card_require_phone_verification", False) is True
        card_locked_reason = (
            "phone_verification_required"
            if require_phone and not is_phone_verified
            else None
        )
        trx_rate_raw = getattr(store, "trx_rate_toman", 0)
        try:
            trx_rate = int(trx_rate_raw) if trx_rate_raw is not None else 0
        except (ValueError, TypeError):
            trx_rate = 0

        if trx_rate <= 0:
            from bot.services.crypto.trx import fetch_trx_rate
            trx_rate = await fetch_trx_rate(0)

        trx_wallet = getattr(store, "trx_wallet_address", "")
        trx_wallet_str = trx_wallet.strip() if isinstance(trx_wallet, str) else ""
        trx_enabled = bool(
            getattr(store, "trx_enabled", False) is True
            and trx_wallet_str
        )

        xrocket_key = getattr(store, "xrocket_api_key", "")
        xrocket_key_str = xrocket_key.strip() if isinstance(xrocket_key, str) else ""
        xrocket_enabled = bool(
            getattr(store, "xrocket_enabled", False) is True
            and xrocket_key_str
        )

        crypto_enabled = getattr(store, "crypto_enabled", False) is True
        ton_wallet = getattr(store, "ton_wallet_address", "")
        ton_wallet_str = ton_wallet.strip() if isinstance(ton_wallet, str) else ""
        ton_rate_raw = getattr(store, "ton_rate_toman", 0)
        try:
            ton_rate_val = int(ton_rate_raw) if ton_rate_raw is not None else 0
        except (ValueError, TypeError):
            ton_rate_val = 0

        tonconnect_enabled = bool(
            crypto_enabled
            and ton_wallet_str
            and ton_rate_val > 0
        )
        usdt_rate_raw = getattr(store, "usdt_rate_toman", 0)
        try:
            usdt_rate = int(usdt_rate_raw) if usdt_rate_raw is not None else 100_000
        except (ValueError, TypeError):
            usdt_rate = 100_000
        if usdt_rate <= 0:
            usdt_rate = 100_000

        stars_rate_raw = getattr(store, "stars_rate_toman", 0)
        try:
            stars_rate = int(stars_rate_raw) if stars_rate_raw is not None else 0
        except (ValueError, TypeError):
            stars_rate = 0
        stars_resolved = resolve_stars_rate(stars_rate, usdt_rate)
        stars_enabled = bool(getattr(store, "stars_enabled", False) is True and stars_resolved > 0)

        payload = {
            "ok": True,
            "min_amount": store.topup_min_amount,
            "card_enabled": bool(store.card_enabled and store.card_number and str(store.card_number).strip()),
            "card_auto_enabled": bool(store.card_auto_enabled and store.card_number and str(store.card_number).strip()),
            "card_number": "" if card_locked_reason else (store.card_number or ""),
            "card_holder": "" if card_locked_reason else (store.card_holder or ""),
            "card_require_phone_verification": require_phone,
            "is_phone_verified": is_phone_verified,
            "card_locked_reason": card_locked_reason,
            "crypto_enabled": bool(store.crypto_enabled and ton_wallet_str and ton_rate_val > 0),
            "ton_wallet_address": ton_wallet_str,
            "ton_rate_toman": ton_rate_val,
            "tonconnect_enabled": tonconnect_enabled,
            "trx_enabled": trx_enabled,
            "trx_wallet_address": trx_wallet_str,
            "trx_rate_toman": trx_rate,
            "xrocket_enabled": xrocket_enabled,
            "usdt_rate_toman": usdt_rate,
            "stars_enabled": stars_enabled,
            "stars_rate_toman": stars_resolved,
        }
        if cache and hasattr(cache, "set"):
            await cache.set(cache_key, payload, ttl_seconds=60)
        return web.json_response(payload)


async def post_user_topup_card(request: web.Request) -> web.Response:
    """Submit card-to-card topup receipt directly from WebApp and alert admins."""
    user_auth, err = require_user(request)
    if err:
        return err

    if user_auth.get("is_preview"):
        return web.json_response({"ok": False, "message": "این عملیات در حالت پیش‌نمایش در دسترس نیست."}, status=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        amount = int(body.get("amount") or 0)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "message": "مبلغ نامعتبر است."}, status=400)
    receipt_info = (body.get("receipt_text") or "").strip()[:500]
    receipt_image = body.get("receipt_image")

    img_bytes = None
    MAX_IMAGE_BYTES = 10 * 1024 * 1024
    if receipt_image and isinstance(receipt_image, str):
        if len(receipt_image) > 15 * 1024 * 1024:
            return web.json_response(
                {"ok": False, "message": "حجم تصویر فیش واریزی نباید بیشتر از ۱۰ مگابایت باشد."},
                status=400,
            )
        if "base64," in receipt_image:
            header = receipt_image.split("base64,")[0].lower()
            if header and not header.startswith("data:image/"):
                return web.json_response(
                    {"ok": False, "message": "فرمت فایل نامعتبر است. لطفاً یک تصویر (JPG/PNG/WEBP) ارسال کنید."},
                    status=400,
                )
            try:
                import base64
                b64_data = receipt_image.split("base64,")[1]
                img_bytes = base64.b64decode(b64_data)
                if len(img_bytes) > MAX_IMAGE_BYTES:
                    return web.json_response(
                        {"ok": False, "message": "حجم تصویر فیش واریزی نباید بیشتر از ۱۰ مگابایت باشد."},
                        status=400,
                    )
            except Exception as b64_err:
                logger.warning("Failed to decode receipt image: %s", b64_err)

    if not img_bytes:
        return web.json_response(
            {"ok": False, "message": "بارگذاری تصویر فیش واریزی الزامی است."},
            status=400,
        )

    telegram_id = int(user_auth["id"])
    bot = request.app["bot"]
    settings = request.app["settings"]

    async with db_session(request) as session:
        store = await get_store_settings(session)
        require_phone = getattr(store, "card_require_phone_verification", False) is True
        if require_phone:
            db_user = None
            if hasattr(session, "execute"):
                try:
                    from bot.db.repositories.user_repo import UserRepository
                    user_repo = UserRepository(session)
                    db_user = await user_repo.get_by_telegram_id(telegram_id)
                except Exception:
                    db_user = None
            if not db_user or not getattr(db_user, "phone_number", None) or not db_user.phone_number.strip():
                return web.json_response(
                    {
                        "ok": False,
                        "error": "phone_required",
                        "message": "جهت پرداخت کارت‌به‌کارت و جلوگیری از سوءاستفاده‌های بانکی، لطفاً ابتدا شماره تماس خود را در ربات تلگرام تأیید نمایید.",
                    },
                    status=403,
                )

        card_num = getattr(store, "card_number", "")
        card_enabled = getattr(store, "card_enabled", True)
        is_empty_card = not (str(card_num).strip() if card_num else "")
        if not card_enabled or is_empty_card:
            return web.json_response(
                {
                    "ok": False,
                    "error": "card_disabled",
                    "message": "پرداخت کارت به کارت در حال حاضر غیرفعال است.",
                },
                status=400,
            )

        if amount < store.topup_min_amount:
            return web.json_response(
                {"ok": False, "message": f"حداقل مبلغ شارژ {store.topup_min_amount:,} تومان است."},
                status=400,
            )

        max_amount = getattr(store, "topup_max_amount", 0)
        if isinstance(max_amount, int | float) and max_amount > 0 and amount > max_amount:
            return web.json_response(
                {"ok": False, "message": f"حداکثر مبلغ شارژ {int(max_amount):,} تومان است."},
                status=400,
            )

        wallet_repo = WalletRepository(session)
        if await wallet_repo.pending_count(telegram_id) >= 3:
            return web.json_response(
                {"ok": False, "message": "شما حداکثر ۳ درخواست در انتظار بررسی دارید. لطفاً تا تعیین تکلیف آن‌ها صبر کنید."},
                status=400,
            )

        img_hash = "img:" + hashlib.sha256(img_bytes).hexdigest()[:48]
        if await wallet_repo.receipt_exists(img_hash):
            return web.json_response(
                {"ok": False, "message": "این فیش واریزی قبلاً ثبت شده است و امکان ارسال مجدد آن وجود ندارد."},
                status=400,
            )

        text_hash = None
        if receipt_info and receipt_info.strip():
            normalized = " ".join(receipt_info.split())
            text_hash = "text:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:48]
            if await wallet_repo.receipt_exists(text_hash):
                return web.json_response(
                    {"ok": False, "message": "این فیش یا شماره پیگیری قبلاً ثبت شده است و امکان ارسال مجدد آن وجود ندارد."},
                    status=400,
                )

        receipt_hash = f"{img_hash}|{text_hash}" if text_hash else img_hash
        try:
            topup = await wallet_repo.create_topup(telegram_id, amount, receipt_hash)

            if img_bytes:
                import asyncio
                from pathlib import Path
                receipt_dir = Path("data/receipts")
                receipt_dir.mkdir(parents=True, exist_ok=True)
                local_file = receipt_dir / f"receipt_{topup.id}.jpg"
                await asyncio.to_thread(local_file.write_bytes, img_bytes)
                topup.receipt_photo_id = f"local:receipt_{topup.id}.jpg"

            await session.commit()
        except IntegrityError:
            await session.rollback()
            return web.json_response(
                {
                    "ok": False,
                    "error": "duplicate_receipt",
                    "message": "این فیش واریزی قبلاً ثبت شده است.",
                },
                status=409,
            )

        # Send alert with inline buttons to admin chat
        admin_chat_id = settings.ADMIN_CHAT_ID
        if admin_chat_id and bot:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ تایید", callback_data=f"topup:ok:{topup.id}")
            kb.button(text="❌ رد", callback_data=f"topup:no:{topup.id}")
            kb.adjust(2)

            thread_kwargs = admin_thread_kwargs(store, settings, kind="topups")

            tg_username = f"@{user_auth.get('username')}" if user_auth.get("username") else "—"
            user_full_name = user_auth.get("first_name", "کاربر")
            if user_auth.get("last_name"):
                user_full_name += f" {user_auth.get('last_name')}"

            safe_info = escape(receipt_info[:200] or ('تصویر فیش پیوست شد' if img_bytes else 'رسید ثبت‌شده در وب‌اپ'))
            caption = (
                f"💳 <b>درخواست شارژ حساب (از طریق مینی‌اپ)</b>\n"
                f"──────────────────\n"
                f"🆔 شناسه درخواست : <code>#{topup.id}</code>\n"
                f"👤 نام کاربر : <b>{escape(user_full_name[:50])}</b>\n"
                f"🔢 شناسه تلگرام : <code>{telegram_id}</code>\n"
                f"🏷 نام کاربری : {escape(tg_username[:50])}\n"
                f"💰 مبلغ شارژ : <b>{amount:,}</b> تومان\n"
                f"📝 اطلاعات رسید / پیگیری :\n<code>{safe_info}</code>"
            )

            try:
                if img_bytes:
                    from aiogram.types import BufferedInputFile
                    photo_file = BufferedInputFile(img_bytes, filename=f"receipt_{topup.id}.jpg")
                    msg_obj = await bot.send_photo(
                        chat_id=admin_chat_id,
                        photo=photo_file,
                        caption=caption,
                        reply_markup=kb.as_markup(),
                        parse_mode="HTML",
                        **thread_kwargs,
                    )
                    if msg_obj and msg_obj.photo:
                        topup.receipt_photo_id = msg_obj.photo[-1].file_id
                else:
                    msg_obj = await bot.send_message(
                        chat_id=admin_chat_id,
                        text=caption,
                        reply_markup=kb.as_markup(),
                        parse_mode="HTML",
                        **thread_kwargs,
                    )
                topup.admin_message_id = msg_obj.message_id
                await session.commit()
            except Exception as exc:
                logger.error("Failed to notify admin of TMA topup: %s", exc)

        return web.json_response({
            "ok": True,
            "message": "رسید شما با موفقیت ثبت شد و پس از بررسی ادمین حساب شما شارژ می‌گردد.",
        })


async def post_user_topup_crypto(request: web.Request) -> web.Response:
    """Create a TON crypto invoice for authenticated user."""
    user_auth, err = require_user(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        amount = int(body.get("amount") or 0)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "message": "مبلغ نامعتبر است."}, status=400)
    telegram_id = int(user_auth["id"])
    async with db_session(request) as session:
        store = await get_store_settings(session)
        if not (store.crypto_enabled and store.ton_wallet_address and store.ton_rate_toman > 0):
            return web.json_response({"ok": False, "message": "پرداخت ارز دیجیتال در حال حاضر غیرفعال است."}, status=400)

        if amount < store.topup_min_amount:
            return web.json_response(
                {"ok": False, "message": f"حداقل مبلغ شارژ {store.topup_min_amount:,} تومان است."},
                status=400,
            )

        max_amount = getattr(store, "topup_max_amount", 0)
        if isinstance(max_amount, int | float) and max_amount > 0 and amount > max_amount:
            return web.json_response(
                {"ok": False, "message": f"حداکثر مبلغ شارژ {int(max_amount):,} تومان است."},
                status=400,
            )

        crypto_repo = CryptoRepository(session)
        ton_amount = round(amount / store.ton_rate_toman, 4)
        nanotons = int(round(ton_amount * 1_000_000_000))
        invoice = await crypto_repo.create_invoice(
            telegram_id=telegram_id,
            amount_toman=amount,
            amount_ton=f"{ton_amount:.4f}",
            nanotons=nanotons,
            pay_address=store.ton_wallet_address,
            expires_minutes=60,
        )
        await session.commit()

        deep_link = f"ton://transfer/{invoice.pay_address}?amount={invoice.nanotons}&text={invoice.comment}"
        universal_link = f"https://app.tonkeeper.com/transfer/{invoice.pay_address}?amount={invoice.nanotons}&text={invoice.comment}"

        return web.json_response({
            "ok": True,
            "invoice": {
                "id": invoice.id,
                "amount_toman": invoice.amount_toman,
                "amount_ton": invoice.amount_ton,
                "nanotons": invoice.nanotons,
                "ton_rate_toman": store.ton_rate_toman,
                "pay_address": invoice.pay_address,
                "comment": invoice.comment,
                "deep_link": deep_link,
                "universal_link": universal_link,
                "expires_minutes": 60,
            }
        })


async def post_user_topup_crypto_check(request: web.Request) -> web.Response:
    """Verify on-chain payment for a TON invoice."""
    user_auth, err = require_user(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        body = {}

    invoice_id = body.get("invoice_id")
    if not invoice_id:
        return web.json_response({"ok": False, "message": "شناسه فاکتور الزامی است."}, status=400)

    try:
        inv_id_int = int(invoice_id)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "message": "شناسه فاکتور نامعتبر است."}, status=400)

    cache: FastCache = request.app["cache"]
    telegram_id = int(user_auth["id"])

    async with db_session(request) as session:
        crypto_repo = CryptoRepository(session)
        inv = await crypto_repo.get_by_id(inv_id_int)
        if not inv or inv.telegram_id != telegram_id:
            return web.json_response({"ok": False, "message": "فاکتور یافت نشد."}, status=404)

        if inv.status == "paid":
            wallet_repo = WalletRepository(session)
            w = await wallet_repo.get_wallet(telegram_id)
            return web.json_response({"ok": True, "paid": True, "balance": w.balance})

        now = datetime.now(timezone.utc)
        inv_created = inv.created_at if (inv.created_at and inv.created_at.tzinfo) else (inv.created_at.replace(tzinfo=timezone.utc) if inv.created_at else now)
        is_recently_expired = (inv.status == "expired" and (now - inv_created) < timedelta(hours=24))

        if inv.status in ("expired", "cancelled") and not is_recently_expired:
            return web.json_response({"ok": False, "message": "فاکتور منقضی یا لغو شده است."}, status=400)

        store = await get_store_settings(session)
        txs = await fetch_ton_transactions(store.ton_wallet_address)
        from bot.services.crypto.ton import verify_and_credit_ton_invoice
        matched, new_bal, _ = await verify_and_credit_ton_invoice(session, inv, txs, allow_expired=True, bot=request.app.get("bot"))
        if matched:
            await session.commit()
            await cache.delete(f"tma:user:{telegram_id}:dashboard")
            return web.json_response({
                "ok": True,
                "paid": True,
                "new_balance": new_bal,
                "message": "پرداخت با موفقیت تایید شد و کیف پول شارژ گردید!",
            })

        return web.json_response({
            "ok": True,
            "paid": False,
            "message": "تراکنش هنوز در شبکه تون شناسایی نشده است. لطفاً چند لحظه بعد دوباره بررسی کنید.",
        })


async def post_user_topup_stars(request: web.Request) -> web.Response:
    """Create a Telegram Stars (XTR) invoice link for the Mini App."""
    user_auth, err = require_user(request)
    if err:
        return err

    if user_auth.get("is_preview"):
        return web.json_response({"ok": False, "message": "این عملیات در حالت پیش‌نمایش در دسترس نیست."}, status=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        amount = int(body.get("amount") or 0)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "message": "مبلغ نامعتبر است."}, status=400)
    telegram_id = int(user_auth.get("id"))

    async with db_session(request) as session:
        store = await get_store_settings(session)
        if not getattr(store, "stars_enabled", False):
            return web.json_response({"ok": False, "message": "پرداخت با استارز در حال حاضر غیرفعال است."}, status=400)

        min_amt = store.topup_min_amount or 10000
        if amount < min_amt:
            return web.json_response({"ok": False, "message": f"حداقل مبلغ شارژ {min_amt:,} تومان است."}, status=400)

        max_amt = getattr(store, "topup_max_amount", 50_000_000) or 50_000_000
        if amount > max_amt:
            return web.json_response({"ok": False, "message": f"حداکثر مبلغ شارژ {max_amt:,} تومان است."}, status=400)

        rate = resolve_stars_rate(
            getattr(store, "stars_rate_toman", 0),
            getattr(store, "usdt_rate_toman", 0),
        )
        if rate <= 0:
            return web.json_response(
                {"ok": False, "message": "نرخ تبدیل تلگرام استارز هنوز توسط مدیریت تنظیم نشده است."},
                status=400,
            )

        stars_count = max(1, round(amount / rate))

        bot = request.app["bot"]
        from aiogram.types import LabeledPrice
        payload = f"stars_topup:{telegram_id}:{amount}:{stars_count}"
        try:
            link = await bot.create_invoice_link(
                title="شارژ کیف پول",
                description=f"شارژ مبلغ {amount:,} تومان در کیف پول کاربری",
                payload=payload,
                currency="XTR",
                prices=[LabeledPrice(label=f"شارژ {amount:,} تومان", amount=stars_count)],
            )
            return web.json_response({
                "ok": True,
                "invoice_link": link,
                "stars": stars_count,
                "amount": amount,
            })
        except Exception as exc:
            logger.exception("Failed to generate stars invoice link: %s", exc)
            return web.json_response({"ok": False, "message": "خطا در تولید فاکتور استارز تلگرام."}, status=500)


async def post_user_redeem_voucher(request: web.Request) -> web.Response:
    """Redeem a credit/gift card code to user's wallet balance."""
    user_auth, err = require_user(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "message": "فرمت داده نامعتبر است."}, status=400)

    code = str(body.get("code") or "").strip()
    if not code:
        return web.json_response({"ok": False, "message": "لطفاً کد شارژ را وارد نمایید."}, status=400)

    telegram_id = int(user_auth["id"])
    from bot.db.repositories.coupon_repo import CouponRepository
    from bot.db.repositories.wallet_repo import WalletRepository

    async with db_session(request) as session:
        coupon_repo = CouponRepository(session)
        wallet_repo = WalletRepository(session)
        ok, amount, msg = await coupon_repo.redeem_credit_voucher(code, telegram_id)
        if not ok:
            return web.json_response({"ok": False, "message": msg}, status=400)

        await session.commit()
        wallet = await wallet_repo.get_wallet(telegram_id)
        new_balance = wallet.balance if wallet else 0
        cache: FastCache = request.app.get("cache")
        if cache:
            await cache.delete(f"tma:user:{telegram_id}:profile")
            await cache.delete(f"tma:user:{telegram_id}:dashboard")
            await cache.delete(f"tma:user:{telegram_id}:dashboard:default")

        return web.json_response({
            "ok": True,
            "amount": amount,
            "new_balance": new_balance,
            "message": msg,
        })


async def post_user_auto_renew(request: web.Request) -> web.Response:
    """Toggle auto-renew for the user's active subscription."""
    user_auth, err = require_user(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "message": "فرمت داده نامعتبر است."}, status=400)

    auto_renew_val = bool(body.get("auto_renew", False))
    telegram_id = int(user_auth["id"])
    from bot.db.repositories.user_repo import UserRepository

    async with db_session(request) as session:
        user_repo = UserRepository(session)
        res = await user_repo.set_auto_renew(telegram_id, auto_renew_val)
        await session.commit()
        cache: FastCache = request.app.get("cache")
        if cache:
            await cache.delete(f"tma:user:{telegram_id}:profile")
            await cache.delete(f"tma:user:{telegram_id}:dashboard")
            await cache.delete(f"tma:user:{telegram_id}:dashboard:default")

        return web.json_response({
            "ok": True,
            "auto_renew": res,
            "message": "تمدید خودکار فعال شد." if res else "تمدید خودکار غیرفعال شد.",
        })


async def post_user_topup_trx(request: web.Request) -> web.Response:
    """Create a TRX (Tron) invoice for authenticated user."""
    user_auth, err = require_user(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        amount = int(body.get("amount") or 0)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "message": "مبلغ نامعتبر است."}, status=400)

    telegram_id = int(user_auth["id"])
    async with db_session(request) as session:
        store = await get_store_settings(session)
        if not (getattr(store, "trx_enabled", False) and getattr(store, "trx_wallet_address", "") and store.trx_wallet_address.strip()):
            return web.json_response({"ok": False, "message": "پرداخت با ترون (TRX) در حال حاضر غیرفعال است."}, status=400)

        if amount < store.topup_min_amount:
            return web.json_response(
                {"ok": False, "message": f"حداقل مبلغ شارژ {store.topup_min_amount:,} تومان است."},
                status=400,
            )

        max_amount = getattr(store, "topup_max_amount", 0)
        if isinstance(max_amount, int | float) and max_amount > 0 and amount > max_amount:
            return web.json_response(
                {"ok": False, "message": f"حداکثر مبلغ شارژ {int(max_amount):,} تومان است."},
                status=400,
            )

        from bot.services.crypto.trx import fetch_trx_rate
        trx_rate = getattr(store, "trx_rate_toman", 0)
        if trx_rate <= 0:
            trx_rate = await fetch_trx_rate(0)

        trx_amount = round(amount / trx_rate, 2)
        if trx_amount <= 0:
            trx_amount = 1.0
        suns = int(round(trx_amount * 1_000_000))

        crypto_repo = CryptoRepository(session)
        invoice = await crypto_repo.create_invoice(
            telegram_id=telegram_id,
            amount_toman=amount,
            amount_ton=f"{trx_amount:.2f}",
            nanotons=suns,
            pay_address=store.trx_wallet_address.strip(),
            expires_minutes=60,
            currency="TRX",
        )
        await session.commit()

        return web.json_response({
            "ok": True,
            "invoice": {
                "id": invoice.id,
                "amount_toman": invoice.amount_toman,
                "amount_trx": f"{trx_amount:.2f}",
                "suns": suns,
                "trx_rate_toman": trx_rate,
                "pay_address": invoice.pay_address,
                "comment": invoice.comment,
                "currency": "TRX",
                "expires_minutes": 60,
            }
        })


async def post_user_topup_trx_verify(request: web.Request) -> web.Response:
    """Verify on-chain TxID for a TRX invoice submitted by user."""
    user_auth, err = require_user(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        body = {}

    invoice_id = body.get("invoice_id")
    tx_hash = (body.get("tx_hash") or "").strip()
    if not invoice_id:
        return web.json_response({"ok": False, "message": "شناسه فاکتور الزامی است."}, status=400)
    if not tx_hash:
        return web.json_response({"ok": False, "message": "لطفاً شناسه تراکنش (TxID) را وارد نمایید."}, status=400)

    try:
        inv_id_int = int(invoice_id)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "message": "شناسه فاکتور نامعتبر است."}, status=400)

    telegram_id = int(user_auth["id"])
    cache: FastCache = request.app.get("cache")

    async with db_session(request) as session:
        crypto_repo = CryptoRepository(session)
        inv = await crypto_repo.get_by_id(inv_id_int)
        if not inv or inv.telegram_id != telegram_id:
            return web.json_response({"ok": False, "message": "فاکتور یافت نشد."}, status=404)

        if inv.status == "paid":
            wallet_repo = WalletRepository(session)
            w = await wallet_repo.get_wallet(telegram_id)
            return web.json_response({"ok": True, "paid": True, "new_balance": (w.balance if w else 0), "message": "این فاکتور قبلاً تسویه شده است."})

        from bot.services.crypto.trx import verify_and_credit_trx_invoice
        ok, new_bal, msg = await verify_and_credit_trx_invoice(
            session=session,
            invoice=inv,
            tx_hash=tx_hash,
            bot=request.app.get("bot"),
        )
        if ok:
            await session.commit()
            if cache:
                await cache.delete(f"tma:user:{telegram_id}:dashboard")
                await cache.delete(f"tma:user:{telegram_id}:profile")
            return web.json_response({
                "ok": True,
                "paid": True,
                "new_balance": new_bal,
                "message": msg,
            })

        return web.json_response({
            "ok": True,
            "paid": False,
            "message": msg,
        })


async def post_user_topup_tonconnect_submit(request: web.Request) -> web.Response:
    """Submit transaction hash from TON Connect 2.0 wallet transaction."""
    user_auth, err = require_user(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        body = {}

    invoice_id = body.get("invoice_id")
    tx_hash = (body.get("tx_hash") or "").strip()
    if not invoice_id:
        return web.json_response({"ok": False, "message": "شناسه فاکتور الزامی است."}, status=400)

    try:
        inv_id_int = int(invoice_id)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "message": "شناسه فاکتور نامعتبر است."}, status=400)

    telegram_id = int(user_auth["id"])
    cache: FastCache = request.app.get("cache")

    async with db_session(request) as session:
        crypto_repo = CryptoRepository(session)
        inv = await crypto_repo.get_by_id(inv_id_int)
        if not inv or inv.telegram_id != telegram_id:
            return web.json_response({"ok": False, "message": "فاکتور یافت نشد."}, status=404)

        if inv.status == "paid":
            wallet_repo = WalletRepository(session)
            w = await wallet_repo.get_wallet(telegram_id)
            return web.json_response({"ok": True, "paid": True, "new_balance": (w.balance if w else 0), "message": "پرداخت قبلاً انجام شده است."})

        store = await get_store_settings(session)
        txs = await fetch_ton_transactions(store.ton_wallet_address)
        from bot.services.crypto.ton import verify_and_credit_ton_invoice
        matched, new_bal, _ = await verify_and_credit_ton_invoice(session, inv, txs, allow_expired=True, bot=request.app.get("bot"))
        if matched:
            await session.commit()
            if cache:
                await cache.delete(f"tma:user:{telegram_id}:dashboard")
                await cache.delete(f"tma:user:{telegram_id}:profile")
            return web.json_response({
                "ok": True,
                "paid": True,
                "new_balance": new_bal,
                "message": "پرداخت با والت رسمی تلگرام با موفقیت تأیید شد!",
            })

        return web.json_response({
            "ok": True,
            "paid": False,
            "message": "تراکنش ثبت شد و در حال پردازش در شبکه تون است. تا لحظاتی دیگر حساب شما شارژ می‌شود.",
        })


async def post_user_topup_xrocket(request: web.Request) -> web.Response:
    """Create an xRocket invoice link for Telegram payments."""
    user_auth, err = require_user(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        amount = int(body.get("amount") or 0)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "message": "مبلغ نامعتبر است."}, status=400)

    telegram_id = int(user_auth["id"])
    currency = str(body.get("currency") or "USDT").upper()

    async with db_session(request) as session:
        store = await get_store_settings(session)
        if not (getattr(store, "xrocket_enabled", False) and getattr(store, "xrocket_api_key", "") and store.xrocket_api_key.strip()):
            return web.json_response({"ok": False, "message": "درگاه xRocket در حال حاضر فعال نیست."}, status=400)

        if amount < store.topup_min_amount:
            return web.json_response(
                {"ok": False, "message": f"حداقل مبلغ شارژ {store.topup_min_amount:,} تومان است."},
                status=400,
            )

        usdt_rate = getattr(store, "usdt_rate_toman", 0) or 100_000
        amount_usd = round(amount / usdt_rate, 2)
        if amount_usd < 0.1:
            amount_usd = 0.1

        from bot.services.crypto.xrocket import XRocketClient
        client = XRocketClient(store.xrocket_api_key)

        host_url = str(request.url.origin())
        callback_url = f"{host_url}/api/webhooks/xrocket"
        payload_str = f"topup:{telegram_id}:{amount}"

        inv_data = await client.create_invoice(
            amount_usd=amount_usd,
            currency=currency,
            description=f"شارژ کیف پول ({amount:,} تومان)",
            payload=payload_str,
            callback_url=callback_url,
        )

        if not inv_data or not inv_data.get("link"):
            return web.json_response({"ok": False, "message": "خطا در ایجاد فاکتور درگاه xRocket."}, status=502)

        return web.json_response({
            "ok": True,
            "pay_url": inv_data.get("link"),
            "xrocket_id": inv_data.get("id"),
            "amount_toman": amount,
            "amount_usd": amount_usd,
            "currency": currency,
        })


async def post_webhook_xrocket(request: web.Request) -> web.Response:
    """Handle incoming payment webhooks from xRocket (pay.xrocket.tg)."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "message": "invalid json"}, status=400)

    data = body.get("data") or {}
    status = str(data.get("status") or body.get("status") or "").upper()
    payload = str(data.get("payload") or body.get("payload") or "")

    if status in ("PAID", "COMPLETED") and payload.startswith("topup:"):
        parts = payload.split(":")
        if len(parts) >= 3:
            try:
                tg_id = int(parts[1])
                toman_amount = int(parts[2])
            except (ValueError, TypeError):
                return web.json_response({"ok": False}, status=400)

            payment_id = str(data.get("id") or body.get("id") or "")
            tx_key = f"xrocket_{payment_id}"

            async with db_session(request) as session:
                wallet_repo = WalletRepository(session)
                if payment_id and await wallet_repo.receipt_exists(tx_key):
                    return web.json_response({"ok": True, "status": "already_processed"})

                new_bal = await wallet_repo.add_balance_atomic(tg_id, toman_amount)
                if payment_id:
                    await wallet_repo.create_topup(tg_id, toman_amount, tx_key)
                await session.commit()

                cache: FastCache = request.app.get("cache")
                if cache:
                    await cache.delete(f"tma:user:{tg_id}:profile")
                    await cache.delete(f"tma:user:{tg_id}:dashboard")

                bot = request.app.get("bot")
                if bot:
                    try:
                        await bot.send_message(
                            chat_id=tg_id,
                            text=f"🚀 <b>پرداخت با درگاه xRocket با موفقیت تأیید شد!</b>\n\n💰 مبلغ: <b>{toman_amount:,} تومان</b>\n💳 موجودی جدید: <b>{new_bal:,} تومان</b>",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

                return web.json_response({"ok": True, "credited": True, "new_balance": new_bal})

    return web.json_response({"ok": True, "status": "ignored"})


async def post_user_topup_card_auto_create(request: web.Request) -> web.Response:
    """Create an automated card-to-card invoice with unique exact amount suffix."""
    user_auth, err = require_user(request)
    if err:
        return err

    if user_auth.get("is_preview"):
        return web.json_response({"ok": False, "message": "این عملیات در حالت پیش‌نمایش در دسترس نیست."}, status=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        amount = int(body.get("amount") or 0)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "message": "مبلغ نامعتبر است."}, status=400)

    telegram_id = int(user_auth["id"])

    async with db_session(request) as session:
        store = await get_store_settings(session)

        # Phone verification check
        require_phone = getattr(store, "card_require_phone_verification", False) is True
        if require_phone:
            db_user = None
            if hasattr(session, "execute"):
                try:
                    from bot.db.repositories.user_repo import UserRepository
                    db_user = await UserRepository(session).get_by_telegram_id(telegram_id)
                except Exception:
                    db_user = None
            if not db_user or not getattr(db_user, "phone_number", None) or not db_user.phone_number.strip():
                return web.json_response(
                    {
                        "ok": False,
                        "error": "phone_required",
                        "message": "جهت پرداخت کارت‌به‌کارت، تأیید شماره همراه الزامی است.",
                    },
                    status=403,
                )

        card_num = getattr(store, "card_number", "")
        card_auto_enabled = getattr(store, "card_auto_enabled", False)
        if not card_auto_enabled or not (str(card_num).strip() if card_num else ""):
            return web.json_response(
                {"ok": False, "error": "card_auto_disabled", "message": "پرداخت خودکار کارت‌به‌کارت در حال حاضر فعال نیست."},
                status=400,
            )

        if amount < store.topup_min_amount:
            return web.json_response(
                {"ok": False, "message": f"حداقل مبلغ شارژ {store.topup_min_amount:,} تومان است."},
                status=400,
            )

        max_amount = getattr(store, "topup_max_amount", 0)
        if isinstance(max_amount, (int, float)) and max_amount > 0 and amount > max_amount:
            return web.json_response(
                {"ok": False, "message": f"حداکثر مبلغ شارژ {int(max_amount):,} تومان است."},
                status=400,
            )

        from bot.services.payment.card_auto_service import generate_card_auto_invoice
        invoice = await generate_card_auto_invoice(
            session=session,
            telegram_id=telegram_id,
            base_amount=amount,
            store=store,
            ttl_minutes=60,
        )
        await session.commit()

        remaining_secs = max(0, int((invoice.expires_at - datetime.now(timezone.utc)).total_seconds()))

        return web.json_response({
            "ok": True,
            "invoice_uuid": invoice.invoice_uuid,
            "base_amount": invoice.base_amount,
            "exact_amount": invoice.exact_amount,
            "exact_rial": invoice.exact_rial,
            "card_number": invoice.card_number,
            "card_holder": invoice.card_holder,
            "status": invoice.status,
            "expires_at": invoice.expires_at.isoformat(),
            "remaining_seconds": remaining_secs,
        })


async def get_user_topup_card_auto_status(request: web.Request) -> web.Response:
    """Check payment status of an automated card-to-card invoice."""
    user_auth, err = require_user(request)
    if err:
        return err

    telegram_id = int(user_auth["id"])
    uuid_str = request.query.get("uuid")

    from bot.db.repositories.card_auto_repo import CardAutoRepository
    async with db_session(request) as session:
        repo = CardAutoRepository(session)
        if uuid_str:
            invoice = await repo.get_invoice_by_uuid(uuid_str)
            if invoice and invoice.telegram_id != telegram_id:
                return web.json_response({"ok": False, "message": "دسترسی غیرمجاز"}, status=403)
        else:
            invoice = await repo.get_active_invoice_by_user(telegram_id)

        if not invoice:
            return web.json_response({"ok": True, "status": "none", "invoice_uuid": None})

        now = datetime.now(timezone.utc)
        if invoice.status == "pending" and invoice.expires_at <= now:
            invoice.status = "expired"
            await session.commit()

        remaining_secs = max(0, int((invoice.expires_at - now).total_seconds()))

        return web.json_response({
            "ok": True,
            "invoice_uuid": invoice.invoice_uuid,
            "status": invoice.status,
            "base_amount": invoice.base_amount,
            "exact_amount": invoice.exact_amount,
            "exact_rial": invoice.exact_rial,
            "remaining_seconds": remaining_secs,
        })


async def post_user_topup_card_auto_cancel(request: web.Request) -> web.Response:
    """Cancel a pending card-to-card invoice."""
    user_auth, err = require_user(request)
    if err:
        return err

    telegram_id = int(user_auth["id"])
    try:
        body = await request.json()
    except Exception:
        body = {}

    uuid_str = body.get("uuid")
    if not uuid_str:
        return web.json_response({"ok": False, "message": "شناسه فاکتور مشخص نشده است."}, status=400)

    from bot.db.repositories.card_auto_repo import CardAutoRepository
    async with db_session(request) as session:
        repo = CardAutoRepository(session)
        cancelled = await repo.cancel_invoice(str(uuid_str), telegram_id)
        if cancelled:
            await session.commit()
            return web.json_response({"ok": True, "status": "cancelled"})
        return web.json_response({"ok": False, "message": "فاکتور معتبر برای لغو یافت نشد."}, status=400)


async def post_webhook_sms(request: web.Request) -> web.Response:
    """Handle incoming bank SMS forwarded from mobile phone."""
    async with db_session(request) as session:
        store = await get_store_settings(session)

        # 1. Authenticate token
        secret = (store.sms_webhook_secret or "").strip()
        auth_header = request.headers.get("Authorization", "")
        token_header = request.headers.get("X-SMS-Token", "")
        token_query = request.query.get("token", "")

        provided_token = ""
        if token_header:
            provided_token = token_header.strip()
        elif auth_header.startswith("Bearer "):
            provided_token = auth_header.split("Bearer ", 1)[1].strip()
        elif token_query:
            provided_token = token_query.strip()

        # If secret configured, verify
        if secret:
            if not provided_token or provided_token != secret:
                return web.json_response({"ok": False, "message": "Unauthorized"}, status=401)

        # 2. Extract sender and message text
        sender = ""
        raw_message = ""

        try:
            body = await request.json()
            if isinstance(body, dict):
                sender = str(body.get("from") or body.get("sender") or body.get("phone") or "")
                raw_message = str(body.get("message") or body.get("text") or body.get("content") or body.get("msg") or "")
                if not provided_token and body.get("token"):
                    if secret and str(body.get("token")).strip() != secret:
                        return web.json_response({"ok": False, "message": "Unauthorized"}, status=401)
        except Exception:
            pass

        if not raw_message:
            try:
                post_data = await request.post()
                sender = str(post_data.get("from") or post_data.get("sender") or post_data.get("phone") or sender)
                raw_message = str(post_data.get("message") or post_data.get("text") or post_data.get("content") or "")
            except Exception:
                pass

        if not raw_message:
            try:
                raw_message = await request.text()
            except Exception:
                pass

        if not raw_message or not raw_message.strip():
            return web.json_response({"ok": False, "message": "Empty message body"}, status=400)

        from bot.services.payment.card_auto_service import process_incoming_sms
        bot = request.app.get("bot")
        settings = request.app.get("settings")
        cache = request.app.get("cache")

        result = await process_incoming_sms(
            session=session,
            bot=bot,
            settings=settings,
            store=store,
            sender=sender or "SMS_Forwarder",
            raw_message=raw_message,
            cache=cache,
        )
        await session.commit()
        return web.json_response(result)



