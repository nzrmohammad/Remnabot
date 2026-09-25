"""Background device monitoring: notify user when a new HWID connects."""
import asyncio
import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.db.repositories.device_repo import DeviceRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)

DEVICE_CHECK_INTERVAL_SECONDS = 60


async def check_account_new_devices(
    bot: Bot,
    session: AsyncSession,
    remnawave: RemnawaveClient,
    account: dict,
    telegram_id: int,
    lang: str = "fa",
) -> list[dict]:
    account_id = str(account.get("id"))
    username = escape(str(account.get("username") or "—"))
    devices = await remnawave.get_user_hwid_devices(int(account_id))
    if not devices:
        return []

    repo = DeviceRepository(session)
    known = await repo.get_known_hwids(account_id)

    # First time seeing this account: seed existing devices silently so we don't spam
    if not known:
        for d in devices:
            hwid = d.get("hwid")
            if hwid:
                await repo.add_device(
                    telegram_id=telegram_id,
                    account_id=account_id,
                    hwid=hwid,
                    platform=d.get("platform"),
                    device_model=d.get("deviceModel"),
                )
        return []

    new_devices = []
    for d in devices:
        hwid = d.get("hwid")
        if not hwid or hwid in known:
            continue

        # Found a NEW device!
        await repo.add_device(
            telegram_id=telegram_id,
            account_id=account_id,
            hwid=hwid,
            platform=d.get("platform"),
            device_model=d.get("deviceModel"),
        )
        new_devices.append(d)

        platform = escape(str(d.get("platform") or "—"))
        model = escape(str(d.get("deviceModel") or "—"))
        ip = escape(str(d.get("requestIp") or "—"))

        text = t(
            lang,
            "device_new_connected",
            username=username,
            platform=platform,
            model=model,
            ip=ip,
        )

        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_devices"), callback_data=f"acc:dev:{account_id}")
        menu_label = "🏠 منوی اصلی" if lang == "fa" else "🏠 Main Menu"
        kb.button(text=menu_label, callback_data="nav:main_menu")
        kb.adjust(1)

        try:
            await bot.send_message(telegram_id, text, reply_markup=kb.as_markup())
            logger.info(
                "New device alert sent to %s for account %s (hwid: %s)",
                telegram_id,
                account_id,
                hwid,
            )
        except TelegramAPIError as exc:
            logger.warning(
                "Failed to send new device notification to %s: %s", telegram_id, exc
            )

    return new_devices


async def run_devices_check(
    bot: Bot,
    session_factory: async_sessionmaker,
    remnawave: RemnawaveClient,
) -> None:
    async with session_factory() as session:
        user_repo = UserRepository(session)
        users = await user_repo.all_users()
        for user in users:
            try:
                accounts = await remnawave.get_users_by_telegram_id(user.telegram_id)
                if not accounts:
                    continue
                lang = user.language or "fa"
                for account in accounts:
                    await check_account_new_devices(
                        bot, session, remnawave, account, user.telegram_id, lang
                    )
            except Exception:  # noqa: BLE001
                logger.exception("device check error for user %s", user.telegram_id)
        await session.commit()


async def devices_loop(
    bot: Bot,
    session_factory: async_sessionmaker,
    remnawave: RemnawaveClient,
) -> None:
    await asyncio.sleep(15)  # let startup finish
    logger.info("devices loop started (every %s s)", DEVICE_CHECK_INTERVAL_SECONDS)
    while True:
        try:
            await run_devices_check(bot, session_factory, remnawave)
        except Exception:  # noqa: BLE001
            logger.exception("devices sweep failed")
        await asyncio.sleep(DEVICE_CHECK_INTERVAL_SECONDS)
