"""Admin panel: admin-managed services (create / edit / enable / delete).

Services are stored in the database (not hardcoded). The admin opens the
panel from the main menu, then manages the list with inline buttons and a
guided text form (FSM). Only users listed in ADMIN_IDS can access it.
"""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.menu import delete_message_silently, render_menu
from bot.services.service_display import service_block
from bot.states.service_admin import ServiceAdminStates

logger = logging.getLogger(__name__)
router = Router(name="admin")

SEPARATOR = "─" * 18

# Persian/Arabic digits → Latin, so «۱۰۰۰۰۰» works too
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# field key -> (prompt text key, kind)
# kinds: "text" | "int" | "opt_text" (/skip -> None) | "opt_int" | "strategy"
EDIT_FIELDS = {
    "name": ("svc_prompt_name", "text"),
    "price": ("svc_prompt_price", "int"),
    "duration": ("svc_prompt_duration", "int"),
    "traffic": ("svc_prompt_traffic", "int"),
    "strategy": ("svc_prompt_strategy", "strategy"),
    "hwid": ("svc_prompt_hwid", "opt_int"),
    "squad": ("svc_prompt_squad", "opt_text"),
    "description": ("svc_prompt_description", "opt_text"),
}

# UI field key -> real DB column on Service (fixes silent no-op edit bug)
FIELD_TO_COLUMN = {
    "name": "name",
    "price": "price",
    "duration": "duration_days",
    "traffic": "traffic_gb",
    "strategy": "traffic_strategy",
    "hwid": "hwid_limit",
    "squad": "squad_uuid",
    "description": "description",
}

ADMIN_EMOJI = {
    "name": "🏷", "price": "💰", "duration": "📅", "traffic": "📊",
    "strategy": "🔁", "hwid": "📱", "squad": "🧩", "description": "📝",
}

STRATEGY_KEYS = ["NO_RESET", "DAY", "WEEK", "MONTH"]


def _is_admin(user_id: int) -> bool:
    return user_id in get_settings().ADMIN_IDS


def _parse_int(text: str) -> int | None:
    cleaned = text.translate(_DIGIT_MAP).replace(",", "").replace("،", "").strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


async def _render_admin_services(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    toast: str | None = None,
) -> None:
    lang = user.language or "fa"
    services = await ServiceRepository(session).list_all()

    lines = [f"{t(lang, 'admin_services_title')}\n{SEPARATOR}"]
    if not services:
        lines.append(t(lang, "services_empty"))
    else:
        hint = (
            "برای مشاهده جزئیات، ویرایش یا فعال/غیرفعال‌سازی، سرویس مورد نظر را انتخاب کنید:"
            if lang == "fa"
            else "Select a service to view details, edit, or toggle status:"
        )
        lines.append(hint)

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        # Group into pairs and reverse each pair for Persian RTL:
        # 1st item appears on the RIGHT, 2nd on the LEFT
        for i in range(0, len(services), 2):
            chunk = services[i : i + 2]
            if len(chunk) == 2:
                for s in reversed(chunk):
                    status_icon = "✅" if s.is_active else "❌"
                    kb.button(text=f"{status_icon} {s.name}", callback_data=f"adm:svc:view:{s.id}")
            else:
                s = chunk[0]
                status_icon = "✅" if s.is_active else "❌"
                kb.button(text=f"{status_icon} {s.name}", callback_data=f"adm:svc:view:{s.id}")
    else:
        for s in services:
            status_icon = "✅" if s.is_active else "❌"
            kb.button(text=f"{status_icon} {s.name}", callback_data=f"adm:svc:view:{s.id}")

    if lang == "fa":
        # Persian RTL: Left = Coupons, Right = Add Service
        kb.button(text=t(lang, "btn_coupons_admin"), callback_data="adm:coupons")
        kb.button(text=t(lang, "btn_add_service"), callback_data="adm:svc:add")
    else:
        kb.button(text=t(lang, "btn_add_service"), callback_data="adm:svc:add")
        kb.button(text=t(lang, "btn_coupons_admin"), callback_data="adm:coupons")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")

    service_sizes = [2] * (len(services) // 2) + ([1] if len(services) % 2 else [])
    sizes = service_sizes + [2, 1, 1]
    kb.adjust(*sizes)

    text = "\n".join(lines)
    if toast:
        text = f"{toast}\n\n{text}"
    await render_menu(bot, user, user_repo, text, kb.as_markup())


async def _render_service_detail(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    service_id: int,
    toast: str | None = None,
) -> None:
    lang = user.language or "fa"
    service = await ServiceRepository(session).get(service_id)
    if service is None:
        await _render_admin_services(bot, user, user_repo, session, toast=t(lang, "acc_error"))
        return

    lines = [
        f"📦 <b>{escape(service.name)}</b>\n{SEPARATOR}",
        service_block(service, lang, show_state=True),
    ]

    kb = InlineKeyboardBuilder()
    toggle_text = "🔴 " + t(lang, "btn_disable") if service.is_active else "🟢 " + t(lang, "btn_enable")
    edit_text = "✏️ " + t(lang, "btn_edit")

    if lang == "fa":
        # Persian RTL: Left = Toggle, Right = Edit
        kb.button(text=toggle_text, callback_data=f"adm:svc:toggle:{service.id}")
        kb.button(text=edit_text, callback_data=f"adm:svc:edit:{service.id}")
    else:
        kb.button(text=edit_text, callback_data=f"adm:svc:edit:{service.id}")
        kb.button(text=toggle_text, callback_data=f"adm:svc:toggle:{service.id}")

    kb.button(text="🗑 " + t(lang, "btn_delete"), callback_data=f"adm:svc:del:{service.id}")
    kb.button(text=t(lang, "btn_back"), callback_data="adm:services")
    kb.adjust(2, 1, 1)

    text = "\n".join(lines)
    if toast:
        text = f"{toast}\n\n{text}"
    await render_menu(bot, user, user_repo, text, kb.as_markup())


def _cancel_kb(lang: str, target: str = "adm:svc:cancel") -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data=target)
    return kb


# --------------------------------------------------------------------- #
# Admin panel entry
# --------------------------------------------------------------------- #
@router.callback_query(F.data == "menu:admin")
async def admin_panel(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    if not _is_admin(call.from_user.id):
        await call.answer(t(call.from_user.language_code, "not_authorized"), show_alert=True)
        return
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        # Persian RTL: first added button appears on LEFT, second on RIGHT
        # Row 1: Left = User Management, Right = Dashboard
        kb.button(text=t(lang, "btn_manage_users"), callback_data="adm:users")
        kb.button(text=t(lang, "btn_dashboard"), callback_data="adm:dash")
        # Row 2: Left = Manage Services, Right = Sales Report
        kb.button(text=t(lang, "btn_manage_services"), callback_data="adm:services")
        kb.button(text=t(lang, "btn_sales_report"), callback_data="adm:sales")
        # Row 3: Left = Broadcast, Right = Store Settings
        kb.button(text=t(lang, "btn_broadcast"), callback_data="adm:broadcast")
        kb.button(text=t(lang, "btn_store_settings"), callback_data="adm:settings")
        # Row 4: Left = Node Monitor, Right = Database Backup
        kb.button(text=t(lang, "btn_nodes_monitor"), callback_data="adm:nodes")
        kb.button(text=t(lang, "btn_backup_db"), callback_data="adm:backup")
    else:
        # LTR: Row 1: Left = Dashboard, Right = User Management
        kb.button(text=t(lang, "btn_dashboard"), callback_data="adm:dash")
        kb.button(text=t(lang, "btn_manage_users"), callback_data="adm:users")
        # Row 2: Left = Sales Report, Right = Manage Services
        kb.button(text=t(lang, "btn_sales_report"), callback_data="adm:sales")
        kb.button(text=t(lang, "btn_manage_services"), callback_data="adm:services")
        # Row 3: Left = Store Settings, Right = Broadcast
        kb.button(text=t(lang, "btn_store_settings"), callback_data="adm:settings")
        kb.button(text=t(lang, "btn_broadcast"), callback_data="adm:broadcast")
        # Row 4: Left = Database Backup, Right = Node Monitor
        kb.button(text=t(lang, "btn_backup_db"), callback_data="adm:backup")
        kb.button(text=t(lang, "btn_nodes_monitor"), callback_data="adm:nodes")
    # Row 5: Main Menu
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    kb.adjust(2, 2, 2, 2, 1)

    await render_menu(
        bot, user, user_repo,
        f"{t(lang, 'admin_panel_title')}\n{SEPARATOR}\n{t(lang, 'admin_panel_hint')}",
        kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "adm:services")
async def admin_services(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_admin_services(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data.startswith("adm:svc:view:"))
async def service_view_detail(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    await state.clear()
    try:
        service_id = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_service_detail(bot, user, user_repo, session, service_id)
    await call.answer()


@router.callback_query(F.data == "adm:svc:cancel")
async def admin_cancel(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    data = await state.get_data()
    service_id = data.get("service_id")
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    if service_id:
        await _render_service_detail(bot, user, user_repo, session, int(service_id))
    else:
        await _render_admin_services(bot, user, user_repo, session)
    await call.answer()


# --------------------------------------------------------------------- #
# Create a service (guided form)
# --------------------------------------------------------------------- #
@router.callback_query(F.data == "adm:svc:add")
async def add_service_start(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    await state.set_state(ServiceAdminStates.create_name)
    await state.update_data(mode="create")
    kb = _cancel_kb(lang)
    await render_menu(
        bot, user, user_repo,
        t(lang, "svc_prompt_name"),
        kb.as_markup(),
    )
    await call.answer()


@router.message(ServiceAdminStates.create_name, F.text)
async def create_name(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    name = message.text.strip()
    if not name:
        await render_menu(
            bot, user, user_repo, t(lang, "svc_invalid_name"), _cancel_kb(lang).as_markup()
        )
        return
    await state.update_data(name=name)
    await state.set_state(ServiceAdminStates.create_price)
    await render_menu(
        bot, user, user_repo, t(lang, "svc_prompt_price"), _cancel_kb(lang).as_markup()
    )


@router.message(ServiceAdminStates.create_price, F.text)
async def create_price(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    value = _parse_int(message.text)
    if value is None or value < 0:
        await render_menu(
            bot, user, user_repo, t(lang, "svc_invalid_number"), _cancel_kb(lang).as_markup()
        )
        return
    await state.update_data(price=value)
    await state.set_state(ServiceAdminStates.create_duration)
    await render_menu(
        bot, user, user_repo, t(lang, "svc_prompt_duration"), _cancel_kb(lang).as_markup()
    )


@router.message(ServiceAdminStates.create_duration, F.text)
async def create_duration(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    value = _parse_int(message.text)
    if value is None or value < 0:
        await render_menu(
            bot, user, user_repo, t(lang, "svc_invalid_number"), _cancel_kb(lang).as_markup()
        )
        return
    await state.update_data(duration=value)
    await state.set_state(ServiceAdminStates.create_traffic)
    await render_menu(
        bot, user, user_repo, t(lang, "svc_prompt_traffic"), _cancel_kb(lang).as_markup()
    )


@router.message(ServiceAdminStates.create_traffic, F.text)
async def create_traffic(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    value = _parse_int(message.text)
    if value is None or value < 0:
        await render_menu(
            bot, user, user_repo, t(lang, "svc_invalid_number"), _cancel_kb(lang).as_markup()
        )
        return
    await state.update_data(traffic=value)
    await state.set_state(ServiceAdminStates.create_strategy)

    kb = InlineKeyboardBuilder()
    for stgy in STRATEGY_KEYS:
        key = {"NO_RESET": "stgy_no_reset", "DAY": "stgy_day",
               "WEEK": "stgy_week", "MONTH": "stgy_month"}[stgy]
        kb.button(text=t(lang, key), callback_data=f"adm:stgy:{stgy}")
    kb.adjust(2, 2)
    await render_menu(bot, user, user_repo, t(lang, "svc_prompt_strategy"), kb.as_markup())


@router.callback_query(ServiceAdminStates.create_strategy, F.data.startswith("adm:stgy:"))
async def create_strategy_pick(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    value = call.data.split(":", 2)[2]
    if value not in STRATEGY_KEYS:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    await state.update_data(strategy=value)
    await state.set_state(ServiceAdminStates.create_hwid)
    await render_menu(
        bot, user, user_repo, t(lang, "svc_prompt_hwid"), _cancel_kb(lang).as_markup()
    )
    await call.answer()


@router.message(ServiceAdminStates.create_hwid, F.text)
async def create_hwid(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    raw = message.text.strip()
    if raw in ("/skip", "-", "—"):
        await state.update_data(hwid=None)
    else:
        value = _parse_int(raw)
        if value is None or value < 0:
            await render_menu(
                bot, user, user_repo, t(lang, "svc_invalid_number"), _cancel_kb(lang).as_markup()
            )
            return
        await state.update_data(hwid=value)
    await state.set_state(ServiceAdminStates.create_squad)
    await render_menu(
        bot, user, user_repo, t(lang, "svc_prompt_squad"), _cancel_kb(lang).as_markup()
    )


@router.message(ServiceAdminStates.create_squad, F.text)
async def create_squad(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    raw = message.text.strip()
    squad = None if raw in ("/skip", "-", "—") else raw
    await state.update_data(squad=squad)
    await state.set_state(ServiceAdminStates.create_description)
    await render_menu(
        bot, user, user_repo, t(lang, "svc_prompt_description"), _cancel_kb(lang).as_markup()
    )


@router.message(ServiceAdminStates.create_description, F.text)
async def create_description(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    text = message.text.strip()
    description = None if text in ("", "/skip", "-", "—") else text
    await state.update_data(description=description)

    data = await state.get_data()
    service = await ServiceRepository(user_repo.session).create(
        name=str(data.get("name", "")),
        price=int(data.get("price", 0)),
        duration_days=int(data.get("duration", 0)),
        traffic_gb=int(data.get("traffic", 0)),
        description=description,
        traffic_strategy=str(data.get("strategy", "NO_RESET")),
        hwid_limit=data.get("hwid"),
        squad_uuid=data.get("squad"),
    )
    await state.clear()
    await _render_service_detail(
        bot, user, user_repo, user_repo.session, service.id,
        toast=t(lang, "svc_created", name=service.name),
    )


# --------------------------------------------------------------------- #
# Edit a service
# --------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("adm:svc:edit:"))
async def edit_service_pick(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        service_id = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    service = await ServiceRepository(session).get(service_id)
    if service is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    await state.set_state(ServiceAdminStates.edit_value)
    await state.update_data(service_id=service_id)

    kb = InlineKeyboardBuilder()
    for field in EDIT_FIELDS:
        kb.button(
            text=f"{ADMIN_EMOJI[field]} {t(lang, f'svc_field_{field}')}",
            callback_data=f"adm:svc:edf:{service_id}:{field}",
        )
    kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:svc:view:{service_id}")
    kb.adjust(2, 2, 2, 2, 1)

    await render_menu(
        bot, user, user_repo,
        f"{t(lang, 'svc_edit_title')}\n\n{service_block(service, lang)}",
        kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:svc:edf:"))
async def edit_service_field(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        _, _, _, service_id_s, field = call.data.split(":", 4)
        service_id = int(service_id_s)
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if field not in EDIT_FIELDS:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    await state.set_state(ServiceAdminStates.edit_value)
    await state.update_data(service_id=int(service_id), field=field)

    prompt_key = EDIT_FIELDS[field][0]
    await render_menu(
        bot, user, user_repo,
        t(lang, prompt_key),
        _cancel_kb(lang, target=f"adm:svc:edit:{service_id}").as_markup(),
    )
    await call.answer()


@router.message(ServiceAdminStates.edit_value, F.text)
async def edit_value_save(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    data = await state.get_data()
    service_id = int(data.get("service_id", 0))
    field = data.get("field", "name")
    kind = EDIT_FIELDS[field][1]
    SKIP_WORDS = ("", "/skip", "-", "—")

    raw = message.text.strip()
    value: str | int | None
    if kind == "int":
        parsed = _parse_int(raw)
        if parsed is None or parsed < 0:
            await render_menu(
                bot, user, user_repo, t(lang, "svc_invalid_number"),
                _cancel_kb(lang, target=f"adm:svc:edit:{service_id}").as_markup(),
            )
            return
        value = parsed
    elif kind == "opt_int":
        if raw in SKIP_WORDS:
            value = None
        else:
            parsed = _parse_int(raw)
            if parsed is None or parsed < 0:
                await render_menu(
                    bot, user, user_repo, t(lang, "svc_invalid_number"),
                    _cancel_kb(lang, target=f"adm:svc:edit:{service_id}").as_markup(),
                )
                return
            value = parsed
    elif kind == "strategy":
        value = raw.upper()
        if value not in STRATEGY_KEYS:
            await render_menu(
                bot, user, user_repo, t(lang, "svc_invalid_strategy"),
                _cancel_kb(lang, target=f"adm:svc:edit:{service_id}").as_markup(),
            )
            return
    else:  # "text" | "opt_text"
        value = None if raw in SKIP_WORDS else raw
        if field == "name" and not value:
            await render_menu(
                bot, user, user_repo, t(lang, "svc_invalid_name"),
                _cancel_kb(lang, target=f"adm:svc:edit:{service_id}").as_markup(),
            )
            return

    repo = ServiceRepository(session)
    service = await repo.update(service_id, **{FIELD_TO_COLUMN[field]: value})
    await state.clear()

    if service is None:
        await _render_admin_services(bot, user, user_repo, session)
        return
    await _render_service_detail(
        bot, user, user_repo, session, service.id,
        toast=t(lang, "svc_updated", name=service.name),
    )


# --------------------------------------------------------------------- #
# Enable / disable / delete
# --------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("adm:svc:toggle:"))
async def toggle_service(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        service_id = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)

    repo = ServiceRepository(session)
    service = await repo.get(service_id)
    if service is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    new_state = not service.is_active
    await repo.set_active(service_id, new_state)
    await _render_service_detail(bot, user, user_repo, session, service_id)
    toast_msg = "✅ سرویس فعال شد." if new_state else "⛔️ سرویس غیرفعال شد."
    await call.answer(toast_msg)


@router.callback_query(F.data.startswith("adm:svc:del:"))
async def delete_service_confirm(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        service_id = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    service = await ServiceRepository(session).get(service_id)
    if service is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.button(
        text=t(lang, "btn_yes_delete"),
        callback_data=f"adm:svc:del_yes:{service.id}",
    )
    kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:svc:view:{service.id}")
    kb.adjust(2)

    await render_menu(
        bot, user, user_repo,
        t(lang, "svc_delete_confirm", name=escape(service.name)),
        kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:svc:del_yes:"))
async def delete_service_do(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        service_id = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    repo = ServiceRepository(session)
    service = await repo.get(service_id)
    if service is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    await repo.delete(service_id)
    await _render_admin_services(
        bot, user, user_repo, session, toast=t(lang, "svc_deleted", name=service.name)
    )
    await call.answer()
