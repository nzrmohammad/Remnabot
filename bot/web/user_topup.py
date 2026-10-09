"""TMA User Wallet and Top-up API endpoints."""
import hashlib
import logging
from html import escape

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

from bot.common import admin_thread_kwargs
from bot.db.repositories.crypto_repo import CryptoRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.app_settings import get_store_settings
from bot.services.crypto.ton import fetch_ton_transactions
from bot.web.auth import get_authenticated_user
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def get_user_topup_info(request: web.Request) -> web.Response:
    """Return payment methods configuration (card and crypto settings)."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    session_factory = request.app["session_factory"]
    from bot.services.app_settings import get_store_settings

    async with session_factory() as session:
        store = await get_store_settings(session)
        return web.json_response({
            "ok": True,
            "min_amount": store.topup_min_amount,
            "card_enabled": bool(store.card_enabled and store.card_number and store.card_number.strip()),
            "card_number": store.card_number or "",
            "card_holder": store.card_holder or "",
            "crypto_enabled": bool(store.crypto_enabled and store.ton_wallet_address and store.ton_rate_toman > 0),
            "ton_wallet_address": store.ton_wallet_address or "",
            "ton_rate_toman": store.ton_rate_toman or 0,
        })


async def post_user_topup_card(request: web.Request) -> web.Response:
    """Submit card-to-card topup receipt directly from WebApp and alert admins."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    if user_auth.get("is_preview"):
        return web.json_response({"ok": False, "message": "این عملیات در حالت پیش‌نمایش در دسترس نیست."}, status=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    amount = int(body.get("amount") or 0)
    receipt_info = (body.get("receipt_text") or "").strip()
    receipt_image = body.get("receipt_image")

    img_bytes = None
    if receipt_image and isinstance(receipt_image, str) and "base64," in receipt_image:
        try:
            import base64
            b64_data = receipt_image.split("base64,")[1]
            img_bytes = base64.b64decode(b64_data)
        except Exception as b64_err:
            logger.warning("Failed to decode receipt image: %s", b64_err)

    if not receipt_info and not img_bytes:
        return web.json_response(
            {"ok": False, "message": "لطفاً شماره پیگیری یا تصویر فیش واریزی را وارد کنید."},
            status=400,
        )

    telegram_id = int(user_auth["id"])
    session_factory = request.app["session_factory"]
    bot = request.app["bot"]
    settings = request.app["settings"]

    async with session_factory() as session:
        store = await get_store_settings(session)
        if amount < store.topup_min_amount:
            return web.json_response(
                {"ok": False, "message": f"حداقل مبلغ شارژ {store.topup_min_amount:,} تومان است."},
                status=400,
            )

        wallet_repo = WalletRepository(session)
        if await wallet_repo.pending_count(telegram_id) >= 3:
            return web.json_response(
                {"ok": False, "message": "شما حداکثر ۳ درخواست در انتظار بررسی دارید. لطفاً تا تعیین تکلیف آن‌ها صبر کنید."},
                status=400,
            )

        if receipt_info:
            normalized = " ".join(receipt_info.split())
            receipt_hash = "text:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:48]
        elif img_bytes:
            receipt_hash = "img:" + hashlib.sha256(img_bytes).hexdigest()[:48]
        else:
            receipt_hash = f"tma:{telegram_id}:{int(time.time())}"

        if await wallet_repo.receipt_exists(receipt_hash):
            return web.json_response(
                {"ok": False, "message": "این فیش یا شماره پیگیری قبلاً ثبت شده است و امکان ارسال مجدد آن وجود ندارد."},
                status=400,
            )

        topup = await wallet_repo.create_topup(telegram_id, amount, receipt_hash)

        if img_bytes:
            from pathlib import Path
            import asyncio
            receipt_dir = Path("data/receipts")
            receipt_dir.mkdir(parents=True, exist_ok=True)
            local_file = receipt_dir / f"receipt_{topup.id}.jpg"
            await asyncio.to_thread(local_file.write_bytes, img_bytes)
            topup.receipt_photo_id = f"local:receipt_{topup.id}.jpg"

        await session.commit()

        # Send alert with inline buttons to admin chat
        admin_chat_id = settings.ADMIN_CHAT_ID
        if admin_chat_id and bot:
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ تایید", callback_data=f"topup:ok:{topup.id}")
            kb.button(text="❌ رد", callback_data=f"topup:no:{topup.id}")
            kb.adjust(2)

            thread_kwargs = admin_thread_kwargs(store, settings, kind="topups")

            tg_username = f"@{user_auth.get('username')}" if user_auth.get("username") else "—"
            user_full_name = user_auth.get("first_name", "کاربر")
            if user_auth.get("last_name"):
                user_full_name += f" {user_auth.get('last_name')}"

            caption = (
                f"💳 <b>درخواست شارژ حساب (از طریق مینی‌اپ)</b>\n"
                f"──────────────────\n"
                f"🆔 شناسه درخواست : <code>#{topup.id}</code>\n"
                f"👤 نام کاربر : <b>{escape(user_full_name)}</b>\n"
                f"🔢 شناسه تلگرام : <code>{telegram_id}</code>\n"
                f"🏷 نام کاربری : {escape(tg_username)}\n"
                f"💰 مبلغ شارژ : <b>{amount:,}</b> تومان\n"
                f"📝 اطلاعات رسید / پیگیری :\n<code>{escape(receipt_info or ('تصویر فیش پیوست شد' if img_bytes else 'رسید ثبت‌شده در وب‌اپ'))}</code>"
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
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    amount = int(body.get("amount") or 0)
    telegram_id = int(user_auth["id"])
    session_factory = request.app["session_factory"]

    async with session_factory() as session:
        store = await get_store_settings(session)
        if not (store.crypto_enabled and store.ton_wallet_address and store.ton_rate_toman > 0):
            return web.json_response({"ok": False, "message": "پرداخت ارز دیجیتال در حال حاضر غیرفعال است."}, status=400)

        if amount < store.topup_min_amount:
            return web.json_response(
                {"ok": False, "message": f"حداقل مبلغ شارژ {store.topup_min_amount:,} تومان است."},
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
            expires_minutes=30,
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
                "pay_address": invoice.pay_address,
                "comment": invoice.comment,
                "deep_link": deep_link,
                "universal_link": universal_link,
                "expires_minutes": 30,
            }
        })


async def post_user_topup_crypto_check(request: web.Request) -> web.Response:
    """Verify on-chain payment for a TON invoice."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    invoice_id = body.get("invoice_id")
    if not invoice_id:
        return web.json_response({"ok": False, "message": "شناسه فاکتور الزامی است."}, status=400)

    session_factory = request.app["session_factory"]
    cache: FastCache = request.app["cache"]
    telegram_id = int(user_auth["id"])

    async with session_factory() as session:
        crypto_repo = CryptoRepository(session)
        inv = await crypto_repo.get_by_id(int(invoice_id))
        if not inv or inv.telegram_id != telegram_id:
            return web.json_response({"ok": False, "message": "فاکتور یافت نشد."}, status=404)

        if inv.status == "paid":
            wallet_repo = WalletRepository(session)
            w = await wallet_repo.get_wallet(telegram_id)
            return web.json_response({"ok": True, "paid": True, "balance": w.balance})

        if inv.status in ("expired", "cancelled"):
            return web.json_response({"ok": False, "message": "فاکتور منقضی یا لغو شده است."}, status=400)

        store = await get_store_settings(session)
        txs = await fetch_ton_transactions(store.ton_wallet_address)
        for tx in txs:
            if tx.get("comment") == inv.comment and tx.get("nanotons", 0) >= inv.nanotons:
                paid_inv = await crypto_repo.mark_paid(inv.id, tx.get("tx_hash", ""))
                if paid_inv:
                    wallet_repo = WalletRepository(session)
                    new_bal = await wallet_repo.add_balance_atomic(telegram_id, inv.amount_toman)
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
