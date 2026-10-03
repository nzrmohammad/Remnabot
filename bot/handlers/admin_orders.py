"""Admin Orders, Sales, Refunds, and Telemetry Reports Hub."""
import logging

from aiogram import Router

from bot.common import is_admin, parse_int
from bot.handlers.admin_orders_detail import (
    GB,
    PLATFORM_EMOJI,
    _back_admin,
    _render_order_detail,
    _revert_panel_subscription,
    order_view_or_refund,
    router as detail_router,
)
from bot.handlers.admin_orders_list import (
    ORDERS_PER_PAGE,
    _render_orders_list,
    admin_noop,
    orders_clear_search,
    orders_filtered_view,
    orders_search_prompt,
    orders_search_submit,
    router as list_router,
)
from bot.handlers.admin_reports_hub import (
    _render_hwid_inspector,
    _render_reports_hub,
    _render_sessions_explorer,
    _render_srh_inspector,
    report_hwid_inspector_handler,
    report_sessions_explorer_handler,
    report_srh_inspector_handler,
    reports_hub_entry,
    router as reports_router,
    trigger_admin_report_handler,
)

logger = logging.getLogger(__name__)

router = Router(name="admin_orders")
router.include_router(reports_router)
router.include_router(list_router)
router.include_router(detail_router)

_is_admin = is_admin
_safe_int = parse_int

__all__ = [
    "router",
    "_is_admin",
    "_safe_int",
    "ORDERS_PER_PAGE",
    "GB",
    "PLATFORM_EMOJI",
    "_back_admin",
    "_revert_panel_subscription",
    "_render_order_detail",
    "order_view_or_refund",
    "_render_orders_list",
    "admin_noop",
    "orders_search_prompt",
    "orders_clear_search",
    "orders_filtered_view",
    "orders_search_submit",
    "_render_reports_hub",
    "reports_hub_entry",
    "trigger_admin_report_handler",
    "_render_hwid_inspector",
    "report_hwid_inspector_handler",
    "_render_srh_inspector",
    "report_srh_inspector_handler",
    "_render_sessions_explorer",
    "report_sessions_explorer_handler",
]
