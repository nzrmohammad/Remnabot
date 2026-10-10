"""Router aggregation. Add new feature routers here.

Order matters: `cleanup` must always stay last.
"""
from aiogram import Router

from bot.handlers import (
    account,
    admin,
    admin_ops,
    admin_users,
    alerts,
    auth,
    cleanup,
    configs,
    guide,
    main_menu,
    payment_stars,
    profile,
    referral,
    service_request,
    settings,
    start,
    stats,
    support,
    wallet,
)


def get_main_router() -> Router:
    router = Router(name="main")
    router.include_router(start.router)
    router.include_router(auth.router)
    router.include_router(payment_stars.router)
    router.include_router(service_request.router)
    router.include_router(stats.router)      # must come BEFORE main_menu ("menu:*" catch-all)
    router.include_router(account.router)    # must come BEFORE main_menu ("menu:*" catch-all)
    router.include_router(guide.router)      # must come BEFORE main_menu ("menu:*" catch-all)
    router.include_router(settings.router)   # must come BEFORE main_menu ("menu:*" catch-all)
    router.include_router(wallet.router)     # must come BEFORE main_menu ("menu:*" catch-all)
    router.include_router(admin.router)      # must come BEFORE main_menu ("menu:*" catch-all)
    router.include_router(admin_users.router)
    router.include_router(admin_ops.router)
    router.include_router(profile.router)    # must come BEFORE main_menu ("menu:*" catch-all)
    router.include_router(support.router)    # must come BEFORE main_menu ("menu:*" catch-all)
    router.include_router(configs.router)    # must come BEFORE main_menu ("menu:*" catch-all)
    router.include_router(referral.router)   # must come BEFORE main_menu ("menu:*" catch-all)
    router.include_router(alerts.router)
    router.include_router(main_menu.router)
    router.include_router(cleanup.router)  # keep last!
    return router
