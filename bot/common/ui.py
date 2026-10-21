"""Common UI elements, separators and visual constants."""
from typing import Any

SEPARATOR: str = "─" * 18


from bot.locales.texts import t


def fmt(amount: int | float) -> str:
    """Format a number with thousands separator commas."""
    return f"{amount:,}"


def back_admin_builder(lang: str = "fa") -> Any:
    """Standard back button returning to the admin menu."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1)
    return kb


_back_admin = back_admin_builder


def admin_thread_kwargs(
    store: Any = None,
    settings: Any = None,
    kind: str | None = None,
    topic_id: int | None = None,
) -> dict[str, int]:
    """Build thread_kwargs (message_thread_id) for sending messages to Telegram admin forum topics."""
    if topic_id is None and (store is not None or settings is not None):
        if kind:
            attr_store = f"topic_{kind}"
            attr_settings = f"ADMIN_TOPIC_{kind.upper()}"
            topic_id = getattr(store, attr_store, None)
            if topic_id is None:
                topic_id = getattr(settings, attr_settings, None)
    return {"message_thread_id": topic_id} if topic_id else {}
