"""Admin Service Management: CRUD, activation toggle, and FSM wizard."""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, is_admin, parse_int, resolve_op
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.menu import delete_message_silently, render_menu
from bot.services.service_display import service_block
from bot.states.service_admin import ServiceAdminStates

logger = logging.getLogger(__name__)
router = Router(name="admin_services_mgmt")

_is_admin = is_admin
_parse_int = parse_int

# field key -> (prompt text key, kind)
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

# UI field key -> real DB column on Service
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


async def _render_admin_services(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    toast: str | None = None,
) -> None:
    service_repo_cls = resolve_op("ServiceRepository", ServiceRepository)
    render_menu_fn = resolve_op("render_menu", render_menu)

    lang = user.language or "fa"
    services = await service_repo_cls(session).list_all()

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
        kb.button(text=t(lang, "btn_coupons_admin"), callback_data="adm:coupons")
        kb.button(text=t(lang, "btn_add_service"), callback_data="adm:svc:add")
    else:
        kb.button(text=t(lang, "btn_add_service"), callback_data="adm:svc:add")
        kb.button(text=t(lang, "btn_coupons_admin"), callback_data="adm:coupons")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")

    service_sizes = [2] * (len(services) // 2) + ([1] if len(services) % 2 else [])
    sizes = service_sizes + [2, 1]
    kb.adjust(*sizes)

    text = "\n".join(lines)
    if toast:
        text = f"{toast}\n\n{text}"
    await render_menu_fn(bot, user, user_repo, text, kb.as_markup())


async def _render_service_detail(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    service_id: int,
    toast: str | None = None,
) -> None:
    service_repo_cls = resolve_op("ServiceRepository", ServiceRepository)
    render_menu_fn = resolve_op("render_menu", render_menu)
    render_services_fn = resolve_op("_render_admin_services", _render_admin_services)

    lang = user.language or "fa"
    service = await service_repo_cls(session).get(service_id)
    if service is None:
        await render_services_fn(bot, user, user_repo, session, toast=t(lang, "acc_error"))
        return

    lines = [
        f"📦 <b>{escape(service.name)}</b>\n{SEPARATOR}",
        service_block(service, lang, show_state=True),
    ]

    kb = InlineKeyboardBuilder()
    toggle_text = t(lang, "btn_disable") if service.is_active else t(lang, "btn_enable")
    edit_text = t(lang, "btn_edit")
    del_text = t(lang, "btn_delete")

    if lang == "fa":
        kb.button(text=toggle_text, callback_data=f"adm:svc:toggle:{service.id}")
        kb.button(text=edit_text, callback_data=f"adm:svc:edit:{service.id}")
    else:
        kb.button(text=edit_text, callback_data=f"adm:svc:edit:{service.id}")
        kb.button(text=toggle_text, callback_data=f"adm:svc:toggle:{service.id}")

    kb.button(text=del_text, callback_data=f"adm:svc:del:{service.id}")
    kb.button(text=t(lang, "btn_back"), callback_data="adm:services")
    kb.adjust(2, 1, 1)

    text = "\n".join(lines)
    if toast:
        text = f"{toast}\n\n{text}"
    await render_menu_fn(bot, user, user_repo, text, kb.as_markup())


def _cancel_kb(lang: str, target: str = "adm:svc:cancel") -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data=target)
    return kb


@router.callback_query(F.data == "adm:services")
async def admin_services(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    await state.clear()
    render_services_fn = resolve_op("_render_admin_services", _render_admin_services)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_services_fn(bot, user, user_repo, session)
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
    render_detail_fn = resolve_op("_render_service_detail", _render_service_detail)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_detail_fn(bot, user, user_repo, session, service_id)
    await call.answer()


@router.callback_query(F.data == "adm:svc:cancel")
async def admin_cancel(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_detail_fn = resolve_op("_render_service_detail", _render_service_detail)
    render_services_fn = resolve_op("_render_admin_services", _render_admin_services)

    data = await state.get_data()
    service_id = data.get("service_id")
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    if service_id:
        await render_detail_fn(bot, user, user_repo, session, int(service_id))
    else:
        await render_services_fn(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:svc:add")
async def add_service_start(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_menu_fn = resolve_op("render_menu", render_menu)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    await state.set_state(ServiceAdminStates.create_name)
    await state.update_data(mode="create")
    kb = _cancel_kb(lang)
    await render_menu_fn(
        bot, user, user_repo,
        t(lang, "svc_prompt_name"),
        kb.as_markup(),
    )
    await call.answer()


@router.message(ServiceAdminStates.create_name, F.text)
async def create_name(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    del_msg_fn = resolve_op("delete_message_silently", delete_message_silently)
    render_menu_fn = resolve_op("render_menu", render_menu)

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await del_msg_fn(bot, message.chat.id, message.message_id)

    name = message.text.strip()
    if not name:
        await render_menu_fn(
            bot, user, user_repo, t(lang, "svc_invalid_name"), _cancel_kb(lang).as_markup()
        )
        return
    await state.update_data(name=name)
    await state.set_state(ServiceAdminStates.create_price)
    await render_menu_fn(
        bot, user, user_repo, t(lang, "svc_prompt_price"), _cancel_kb(lang).as_markup()
    )


@router.message(ServiceAdminStates.create_price, F.text)
async def create_price(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    del_msg_fn = resolve_op("delete_message_silently", delete_message_silently)
    render_menu_fn = resolve_op("render_menu", render_menu)

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await del_msg_fn(bot, message.chat.id, message.message_id)

    value = _parse_int(message.text)
    if value is None or value < 0:
        await render_menu_fn(
            bot, user, user_repo, t(lang, "svc_invalid_number"), _cancel_kb(lang).as_markup()
        )
        return
    await state.update_data(price=value)
    await state.set_state(ServiceAdminStates.create_duration)
    await render_menu_fn(
        bot, user, user_repo, t(lang, "svc_prompt_duration"), _cancel_kb(lang).as_markup()
    )


@router.message(ServiceAdminStates.create_duration, F.text)
async def create_duration(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    del_msg_fn = resolve_op("delete_message_silently", delete_message_silently)
    render_menu_fn = resolve_op("render_menu", render_menu)

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await del_msg_fn(bot, message.chat.id, message.message_id)

    value = _parse_int(message.text)
    if value is None or value < 0:
        await render_menu_fn(
            bot, user, user_repo, t(lang, "svc_invalid_number"), _cancel_kb(lang).as_markup()
        )
        return
    await state.update_data(duration=value)
    await state.set_state(ServiceAdminStates.create_traffic)
    await render_menu_fn(
        bot, user, user_repo, t(lang, "svc_prompt_traffic"), _cancel_kb(lang).as_markup()
    )


@router.message(ServiceAdminStates.create_traffic, F.text)
async def create_traffic(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    del_msg_fn = resolve_op("delete_message_silently", delete_message_silently)
    render_menu_fn = resolve_op("render_menu", render_menu)

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await del_msg_fn(bot, message.chat.id, message.message_id)

    value = _parse_int(message.text)
    if value is None or value < 0:
        await render_menu_fn(
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
    await render_menu_fn(bot, user, user_repo, t(lang, "svc_prompt_strategy"), kb.as_markup())


@router.callback_query(ServiceAdminStates.create_strategy, F.data.startswith("adm:stgy:"))
async def create_strategy_pick(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_menu_fn = resolve_op("render_menu", render_menu)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    value = call.data.split(":", 2)[2]
    if value not in STRATEGY_KEYS:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    await state.update_data(strategy=value)
    await state.set_state(ServiceAdminStates.create_hwid)
    await render_menu_fn(
        bot, user, user_repo, t(lang, "svc_prompt_hwid"), _cancel_kb(lang).as_markup()
    )
    await call.answer()


@router.message(ServiceAdminStates.create_hwid, F.text)
async def create_hwid(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    del_msg_fn = resolve_op("delete_message_silently", delete_message_silently)
    render_menu_fn = resolve_op("render_menu", render_menu)

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await del_msg_fn(bot, message.chat.id, message.message_id)

    raw = message.text.strip()
    if raw in ("/skip", "-", "—"):
        await state.update_data(hwid=None)
    else:
        value = _parse_int(raw)
        if value is None or value < 0:
            await render_menu_fn(
                bot, user, user_repo, t(lang, "svc_invalid_number"), _cancel_kb(lang).as_markup()
            )
            return
        await state.update_data(hwid=value)
    await state.set_state(ServiceAdminStates.create_squad)
    await render_menu_fn(
        bot, user, user_repo, t(lang, "svc_prompt_squad"), _cancel_kb(lang).as_markup()
    )


@router.message(ServiceAdminStates.create_squad, F.text)
async def create_squad(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    del_msg_fn = resolve_op("delete_message_silently", delete_message_silently)
    render_menu_fn = resolve_op("render_menu", render_menu)

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await del_msg_fn(bot, message.chat.id, message.message_id)

    raw = message.text.strip()
    squad = None if raw in ("/skip", "-", "—") else raw
    await state.update_data(squad=squad)
    await state.set_state(ServiceAdminStates.create_description)
    await render_menu_fn(
        bot, user, user_repo, t(lang, "svc_prompt_description"), _cancel_kb(lang).as_markup()
    )


@router.message(ServiceAdminStates.create_description, F.text)
async def create_description(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    del_msg_fn = resolve_op("delete_message_silently", delete_message_silently)
    service_repo_cls = resolve_op("ServiceRepository", ServiceRepository)
    render_detail_fn = resolve_op("_render_service_detail", _render_service_detail)

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await del_msg_fn(bot, message.chat.id, message.message_id)

    text = message.text.strip()
    description = None if text in ("", "/skip", "-", "—") else text
    await state.update_data(description=description)

    data = await state.get_data()
    service = await service_repo_cls(user_repo.session).create(
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
    await render_detail_fn(
        bot, user, user_repo, user_repo.session, service.id,
        toast=t(lang, "svc_created", name=service.name),
    )


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

    service_repo_cls = resolve_op("ServiceRepository", ServiceRepository)
    render_menu_fn = resolve_op("render_menu", render_menu)

    service = await service_repo_cls(session).get(service_id)
    if service is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    await state.set_state(ServiceAdminStates.edit_value)
    await state.update_data(service_id=service_id)

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        field_pairs = [
            ("price", "name"),
            ("traffic", "duration"),
            ("hwid", "strategy"),
            ("description", "squad"),
        ]
    else:
        field_pairs = [
            ("name", "price"),
            ("duration", "traffic"),
            ("strategy", "hwid"),
            ("squad", "description"),
        ]

    for left_f, right_f in field_pairs:
        kb.button(
            text=f"{ADMIN_EMOJI[left_f]} {t(lang, f'svc_field_{left_f}')}",
            callback_data=f"adm:svc:edf:{service_id}:{left_f}",
        )
        kb.button(
            text=f"{ADMIN_EMOJI[right_f]} {t(lang, f'svc_field_{right_f}')}",
            callback_data=f"adm:svc:edf:{service_id}:{right_f}",
        )
    kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:svc:view:{service_id}")
    kb.adjust(2, 2, 2, 2, 1)

    await render_menu_fn(
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

    render_menu_fn = resolve_op("render_menu", render_menu)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    await state.set_state(ServiceAdminStates.edit_value)
    await state.update_data(service_id=int(service_id), field=field)

    prompt_key = EDIT_FIELDS[field][0]
    await render_menu_fn(
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
    del_msg_fn = resolve_op("delete_message_silently", delete_message_silently)
    render_menu_fn = resolve_op("render_menu", render_menu)
    service_repo_cls = resolve_op("ServiceRepository", ServiceRepository)
    render_services_fn = resolve_op("_render_admin_services", _render_admin_services)
    render_detail_fn = resolve_op("_render_service_detail", _render_service_detail)

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await del_msg_fn(bot, message.chat.id, message.message_id)

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
            await render_menu_fn(
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
                await render_menu_fn(
                    bot, user, user_repo, t(lang, "svc_invalid_number"),
                    _cancel_kb(lang, target=f"adm:svc:edit:{service_id}").as_markup(),
                )
                return
            value = parsed
    elif kind == "strategy":
        value = raw.upper()
        if value not in STRATEGY_KEYS:
            await render_menu_fn(
                bot, user, user_repo, t(lang, "svc_invalid_strategy"),
                _cancel_kb(lang, target=f"adm:svc:edit:{service_id}").as_markup(),
            )
            return
    else:  # "text" | "opt_text"
        value = None if raw in SKIP_WORDS else raw
        if field == "name" and not value:
            await render_menu_fn(
                bot, user, user_repo, t(lang, "svc_invalid_name"),
                _cancel_kb(lang, target=f"adm:svc:edit:{service_id}").as_markup(),
            )
            return

    repo = service_repo_cls(session)
    service = await repo.update(service_id, **{FIELD_TO_COLUMN[field]: value})
    await state.clear()

    if service is None:
        await render_services_fn(bot, user, user_repo, session)
        return
    await render_detail_fn(
        bot, user, user_repo, session, service.id,
        toast=t(lang, "svc_updated", name=service.name),
    )


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
    service_repo_cls = resolve_op("ServiceRepository", ServiceRepository)
    render_detail_fn = resolve_op("_render_service_detail", _render_service_detail)

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    repo = service_repo_cls(session)
    service = await repo.get(service_id)
    if service is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    new_state = not service.is_active
    await repo.set_active(service_id, new_state)
    await render_detail_fn(bot, user, user_repo, session, service_id)
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
    service_repo_cls = resolve_op("ServiceRepository", ServiceRepository)
    render_menu_fn = resolve_op("render_menu", render_menu)

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    service = await service_repo_cls(session).get(service_id)
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

    await render_menu_fn(
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
    service_repo_cls = resolve_op("ServiceRepository", ServiceRepository)
    render_services_fn = resolve_op("_render_admin_services", _render_admin_services)

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    repo = service_repo_cls(session)
    service = await repo.get(service_id)
    if service is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    await repo.delete(service_id)
    await render_services_fn(
        bot, user, user_repo, session, toast=t(lang, "svc_deleted", name=service.name)
    )
    await call.answer()
