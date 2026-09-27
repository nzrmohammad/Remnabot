"""All bot texts. Add a new language by adding a new key to TEXTS."""

# Shown before the user has picked a language → must be bilingual.
CHOOSE_LANGUAGE = (
    "🌐 <b>Please choose your language</b>\n"
    "🌐 <b>لطفاً زبان خود را انتخاب کنید</b>"
)

# Shown to brand-new users while maintenance mode is on → must be bilingual.
MAINTENANCE_NOTICE = (
    "🛠 <b>The bot is under maintenance. Please try again later.</b>\n"
    "🛠 <b>ربات در حال بروزرسانی است. لطفاً کمی بعد دوباره تلاش کنید.</b>"
)

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": (
            "👋 <b>Welcome!</b>\n\n"
            "Please choose one of the options below:"
        ),
        "btn_login": "🔑 Login",
        "btn_new_service": "🎁 Trial Service",
        "btn_back": "🔙 Back",
        "btn_back_to_menu": "🔙 Main Menu",
        "login_failed": (
            "❌ <b>Login failed</b>\n\n"
            "Your Telegram ID was not found in the panel.\n"
            "If you don't have an account yet, go back and use "
            "<b>Request New Service</b>."
        ),
        "service_request_prompt": (
            "💬 <b>Hi! Please leave your message, we will reply soon.</b>\n\n"
            "Send your request in a single message:"
        ),
        "service_request_sent": (
            "✅ <b>Your message has been sent.</b>\n\n"
            "Our team will contact you as soon as possible."
        ),
        "main_menu_title": (
            "🏠 <b>Main Menu</b>\n\n"
            "Choose a section:"
        ),
        "btn_quick_stats": "📊 Quick Stats",
        "btn_account_mgmt": "🛠 Account Management",
        "btn_wallet": "👛 Wallet",
        "btn_services": "📦 Services",
        "btn_connection_guide": "📚 Connection Guide",
        "btn_settings": "⚙️ Settings",
        "btn_support": "🎧 Support",
        "btn_profile": "👤 My Account",
        "btn_admin_panel": "🔐 Admin Panel",
        "section_placeholder": (
            "🚧 <b>{section}</b>\n\n"
            "This section is under construction."
        ),
        "not_authorized": "⛔️ You are not allowed to access this section.",
        "not_verified": (
            "🚫 <b>You are not verified.</b>\n\n"
            "Your Telegram ID was not found in the panel.\n"
            "Please login first, or request a new service."
        ),
        "btn_refresh": "🔄 Refresh",
        "stats_title": "⚡️ <b>Quick Stats</b>",
        "stats_account": "👤 Account",
        "stats_status": "📌 Status",
        "stats_total": "📊 Total Volume",
        "stats_used": "🔥 Used",
        "stats_remaining": "📥 Remaining",
        "stats_unlimited": "♾ Unlimited",
        "stats_expire": "📅 Expires",
        "stats_days_left": "{days} days left",
        "stats_expired_ago": "expired {days} days ago",
        "stats_no_expire": "♾ No expiration",
        "stats_today": "⚡️ Today's usage",
        "stats_lifetime": "📈 Lifetime usage",
        "stats_burn_rate": "⏳ At your current usage rate, remaining data will last about <b>{days} days</b>.",
        "stats_sparkline": "📊 Last 7 days trend : <code>{bars}</code> (<b>{total}</b>)",
        "stats_online_label": "📶 Connection",
        "stats_online_now": "🟢",
        "stats_never_connected": "⚪️",
        "stats_multi_header": "🔗 <b>{count} accounts</b> are linked to your Telegram:",
        "stats_error": "⚠️ Could not fetch stats from the panel. Please try again later.",
        "status_active": "✅",
        "status_disabled": "⛔️",
        "status_limited": "🚫",
        "status_expired": "⏰",
        # --- account management ---
        "acc_title": "🛠 <b>Account Management</b>",
        "acc_pick": "Choose an account:",
        "acc_sub_link": "📥 Subscription link (tap to copy):",
        "btn_open_sub": "🔗 Open link",
        "btn_devices": "📱 Connected devices",
        "btn_revoke": "🔄 Regenerate link",
        "btn_qr": "🧾 QR Code",
        "btn_close": "❌ Close",
        "btn_cancel": "🔙 Cancel",
        "qr_caption": (
            "🧾 <b>Subscription QR Code</b>\n"
            "Scan it in your app to import the subscription.\n\n"
            "<code>{link}</code>"
        ),
        "acc_error": "⚠️ Operation failed. Please try again later.",
        "devices_title": "📱 <b>Connected devices</b>",
        "devices_count": "🔢 Devices",
        "devices_empty": "No devices are registered on this account yet.",
        "device_last_seen": "🕓 Last seen",
        "device_ip": "🌍 IP",
        "btn_device_delete": "❌ Remove device {num}",
        "device_delete_confirm": (
            "❌ <b>Remove this device?</b>\n\n"
            "{device}\n\n"
            "It will be disconnected and its slot freed. "
            "The device can register again the next time it connects."
        ),
        "btn_yes_delete": "✅ Yes, remove",
        "device_deleted": "✅ Device removed.",
        "device_new_connected": (
            "🔔 <b>New device connected!</b>\n\n"
            "👤 Account : <code>{username}</code>\n"
            "📱 Platform : <b>{platform}</b>\n"
            "🏷 Device Model : <b>{model}</b>\n"
            "🌍 IP : <code>{ip}</code>\n\n"
            "⚠️ If this was not you, please check or remove the device in Account Management."
        ),
        "revoke_confirm": (
            "🔄 <b>Regenerate subscription link?</b>\n\n"
            "⚠️ Your <b>current link will stop working immediately</b>.\n"
            "You must add the new link to all of your apps again.\n\n"
            "Use this if your link was shared or leaked."
        ),
        "btn_yes_revoke": "✅ Yes, regenerate",
        "revoke_done": (
            "✅ <b>Subscription link regenerated!</b>\n\n"
            "Your old link no longer works. New link (tap to copy):"
        ),
        # --- connection guide ---
        "guide_title": "📚 <b>Connection Guide</b>",
        "guide_pick": "Choose your operating system:",
        "guide_steps": (
            "1️⃣ Install one of the apps below.\n"
            "2️⃣ Copy your subscription link (tap it below 👇).\n"
            "3️⃣ In the app choose <b>Add Subscription / Import from clipboard</b>.\n"
            "4️⃣ Pick a server and connect."
        ),
        "guide_your_link": "📥 Your subscription link (tap to copy):",
        "btn_platform_android": "🤖 Android",
        "btn_platform_ios": "🍏 iPhone",
        "btn_platform_windows": "🖥 Windows",
        "btn_platform_macos": "💻 macOS",
        "btn_platform_linux": "🐧 Linux",
        # --- settings ---
        "settings_title": "⚙️ <b>Settings</b>",
        "settings_traffic_label": "🔔 Volume alert",
        "settings_expire_label": "⏰ Expiry alert",
        "settings_traffic_hint": "You get a warning once your usage passes this percentage.",
        "settings_expire_hint": "You get a warning this many days before your service expires.",
        "settings_percent_value": "{percent}%",
        "settings_days_value": "{days} days",
        "alerts_off": "Off",
        "btn_set_traffic": "🔔 Change volume alert",
        "btn_set_expire": "⏰ Change expiry alert",
        "settings_pick_traffic": "Warn me when usage passes:",
        "settings_pick_expire": "Warn me this many days before expiry:",
        "settings_saved": "✅ Saved",
        # --- alerts ---
        "alert_traffic": (
            "⚠️ <b>Volume alert</b>\n\n"
            "👤 Account : <code>{username}</code>\n"
            "🔥 You have used <b>{percent}%</b> of your volume.\n"
            "📥 Remaining : <b>{remaining}</b>\n\n"
            "Renew or upgrade now to avoid disconnection 👇"
        ),
        "alert_expire": (
            "⏰ <b>Expiry alert</b>\n\n"
            "👤 Account : <code>{username}</code>\n"
            "📅 Only <b>{days} days</b> left until your service expires ({date}).\n\n"
            "Renew now to avoid disconnection 👇"
        ),
        "alert_expire_now": (
            "⏰ <b>Expiry alert</b>\n\n"
            "👤 Account : <code>{username}</code>\n"
            "📅 Your service <b>expires today or has already expired</b> ({date}).\n\n"
            "Renew now to get reconnected 👇"
        ),
        # --- wallet ---
        "wallet_title": "👛 <b>Wallet</b>",
        "wallet_balance": "💰 Balance : <b>{balance} Toman</b>",
        "wallet_pending": "⏳ {count} top-up request(s) awaiting approval.",
        "btn_topup": "➕ Top up wallet",
        "topup_amount_prompt": (
            "💳 <b>Wallet Top-up</b>\n\n"
            "Please send the amount in Toman (minimum {min} Toman), "
            "or select one of the quick amounts below:"
        ),
        "topup_amount_invalid": (
            "❌ Invalid amount. Send a plain number in Toman (minimum {min})."
        ),
        "topup_card_info": (
            "💳 Transfer <b>{amount} Toman</b> to this card:\n\n"
            "<code>{card}</code>\n"
            "👤 {holder}\n\n"
            "Then send a <b>photo of the receipt</b> (or its text) right here."
        ),
        "topup_no_card": "⚠️ Top-up is currently unavailable. Please contact support.",
        "topup_receipt_registered": (
            "✅ <b>Your receipt was submitted.</b>\n\n"
            "Once the admin approves it, your wallet will be charged and "
            "you will be notified."
        ),
        "topup_approved_user": (
            "✅ <b>Your {amount} Toman top-up was approved!</b>\n"
            "💰 New balance : <b>{balance} Toman</b>"
        ),
        "topup_rejected_user": (
            "❌ <b>Your {amount} Toman top-up was rejected.</b>\n"
            "If you think this is a mistake, contact support."
        ),
        "admin_topup_request": (
            "💳 <b>Wallet top-up request</b> #{id}\n\n"
            "👤 {name}\n"
            "🆔 <code>{tid}</code>\n"
            "🔗 {username}\n"
            "💰 Amount : <b>{amount} Toman</b>\n\n"
            "⬆️ Receipt is the message above."
        ),
        "btn_approve": "✅ Approve",
        "btn_reject": "❌ Reject",
        "admin_topup_done": "✅ Approved — wallet charged.",
        "admin_topup_rejected": "❌ Rejected.",
        "admin_topup_already": "Already decided.",
        "topup_pending_limit": (
            "⏳ You already have 3 pending top-up requests. "
            "Please wait for the admin to review them."
        ),
        "topup_receipt_invalid": (
            "❌ Invalid receipt. Send a photo (up to 10 MB) or a PDF."
        ),
        "topup_duplicate_receipt": (
            "⚠️ This receipt was already submitted. "
            "Please send a new receipt or wait for the review."
        ),
        "topups_history_title": "🧾 <b>Account Ledger & Transactions</b>",
        "topups_history_empty": "No transactions found.",
        "btn_topup_history": "🧾 Account Ledger",
        "topup_status_pending": "⏳ Pending",
        "topup_status_approved": "✅ Approved",
        "topup_status_rejected": "❌ Rejected",
        "tx_topup": "Wallet top-up",
        "tx_topup_pending": "Top-up request (pending)",
        "tx_topup_rejected": "Top-up request (rejected)",
        "tx_order_paid": "Service purchase/renewal",
        "tx_order_refunded": "Refund to wallet",
        "btn_language": "🌐 Language",
        # --- reports ---
        "nightly_title": "🌙 <b>Nightly report</b>",
        "weekly_title": "📊 <b>Weekly report</b>",
        "weekly_day": "▪️ {date} : <b>{total}</b>",
        "weekly_others": "others",
        "weekly_total": "📊 Total this week : <b>{total}</b>",
        "weekly_hi": "Hi {name} 👋",
        "weekly_sum_total": "You used <b>{total}</b> this week.",
        "weekly_sum_more": "That's {percent}% more than last week.",
        "weekly_sum_less": "That's {percent}% less than last week.",
        "weekly_sum_same": "About the same as last week.",
        "weekly_sum_top": (
            "Your busiest day was <b>{day}</b> and you mostly used the "
            "{flag} <b>{node}</b> server."
        ),
        "monthly_title": "🗓 <b>Monthly report — {month}</b>",
        "monthly_day": "▪️ {date} : <b>{total}</b>",
        "monthly_others": "others",
        "monthly_total": "📊 Total this month : <b>{total}</b>",
        "monthly_hi": "Hi {name} 👋",
        "monthly_sum_total": "You used <b>{total}</b> in {month}.",
        "monthly_sum_more": "That's {percent}% more than last month.",
        "monthly_sum_less": "That's {percent}% less than last month.",
        "monthly_sum_same": "About the same as last month.",
        "monthly_sum_top": (
            "Your busiest day was <b>{day}</b> and you mostly used the "
            "{flag} <b>{node}</b> server."
        ),
        "report_used_breakdown": "🔥 Used volume (per server) :",
        "report_today_breakdown": "⚡️ Today's usage :",
        "settings_nightly_label": "🌙 Nightly report",
        "settings_weekly_label": "📊 Weekly report",
        "settings_nightly_hint": "A usage summary every night at 23:59.",
        "settings_weekly_hint": "A full usage report every Friday night at 23:59.",
        "settings_monthly_label": "🗓 Monthly report",
        "settings_monthly_hint": "A full usage report on the last day of the Jalali month at 23:59.",
        "toggle_on": "On",
        "toggle_off": "Off",
        "btn_toggle_nightly": "🌙 Nightly report: {state}",
        "btn_toggle_weekly": "📊 Weekly report: {state}",
        "btn_toggle_monthly": "🗓 Monthly report: {state}",
        # --- services ---
        "services_title": "📦 <b>Services</b>",
        "services_active_empty": "No services are available right now. Please try again later.",
        "btn_request": "📨 Request this service",
        "svc_view_title": "📦 <b>{name}</b>",
        "svc_request_sent": (
            "✅ <b>Your request has been sent.</b>\n\n"
            "Our team will contact you as soon as possible."
        ),
        "svc_field_name": "Name",
        "svc_field_price": "Price",
        "svc_field_duration": "Duration",
        "svc_field_traffic": "Traffic",
        "svc_field_description": "Description",
        "svc_currency": "Toman",
        "unlimited": "♾ Unlimited",
        "svc_days": "{days} days",
        "svc_gb": "{gb} GB",
        "services_policy_hint": (
            "💡 <b>Traffic Policy Note:</b>\n"
            "For plans with '<b>♾ No Reset</b>' strategy, renewing within <b>1 day</b> "
            "after expiration carries over your unused traffic to the next period. "
            "For all other reset periods (Daily, Weekly, Monthly), traffic resets at each renewal."
        ),
        # --- admin panel / services management ---
        "admin_panel_title": "🔐 <b>Admin Panel</b>",
        "admin_panel_hint": "Manage services and other settings here.",
        "btn_manage_services": "📦 Manage Services",
        "admin_services_title": "📦 <b>Services management</b>",
        "services_empty": "No services yet. Add one below 👇",
        "btn_add_service": "➕ Add Service",
        "btn_edit": "✏️ Edit",
        "btn_delete": "🗑 Delete",
        "btn_enable": "✅ Enable",
        "btn_disable": "⛔️ Disable",
        "svc_state_active": "✅ Active",
        "svc_state_inactive": "⛔️ Inactive",
        "svc_prompt_name": "🏷 Send the service <b>name</b>:",
        "svc_prompt_price": "💰 Send the <b>price</b> in Toman:",
        "svc_prompt_duration": "📅 Send the <b>duration</b> in days (0 = unlimited):",
        "svc_prompt_traffic": "📊 Send the <b>traffic</b> in GB (0 = unlimited):",
        "svc_prompt_description": "📝 Send a short <b>description</b> (or send /skip):",
        "svc_invalid_number": "❌ Invalid number. Please send a plain number.",
        "svc_invalid_name": "❌ Name cannot be empty.",
        "svc_created": "✅ Service created: <b>{name}</b>",
        "svc_updated": "✅ Service updated: <b>{name}</b>",
        "svc_deleted": "🗑 Service deleted: <b>{name}</b>",
        "svc_delete_confirm": "🗑 <b>Delete this service?</b>\n\n<b>{name}</b>",
        "svc_edit_title": "✏️ <b>Edit service</b> — choose a field:",
        "svc_requested_admin_title": "New service request",
        "svc_requested_user": "User",
        "svc_requested_username": "Username",
        # --- automatic purchase ---
        "btn_buy": "🛒 Buy",
        "btn_confirm_pay": "✅ Pay & Activate",
        "buy_confirm_title": "🧾 <b>Confirm purchase</b>",
        "buy_current_balance": "Current balance",
        "buy_insufficient": (
            "❌ <b>Insufficient balance.</b>\n\n"
            "💰 Price : <b>{price}</b> {currency}\n"
            "👛 Your balance : <b>{balance}</b> {currency}\n\n"
            "Please top up your wallet first."
        ),
        "buy_choose_account": (
            "🤔 <b>You have more than one account.</b>\n\n"
            "Which one should we renew?"
        ),
        "buy_success": "Purchase successful",
        "buy_success_link": (
            "🔗 <b>Subscription link:</b>\n"
            "<code>{url}</code>\n\n"
            "The link is also available in «Account Management»."
        ),
        "buy_remaining_balance": "👛 Remaining balance : <b>{balance}</b> {currency}",
        "buy_failed": (
            "❌ <b>Activation failed.</b>\n\n"
            "No money was charged. Please try again."
        ),
        "buy_admin_log": "New purchase",
        # --- service extras: strategy / hwid / squad ---
        "svc_prompt_strategy": "🔁 Choose the traffic reset strategy:",
        "svc_prompt_hwid": "📱 Send max device limit (or /skip for panel default - Unlimited):",
        "svc_prompt_squad": "🧩 Send the internal squad UUID (or /skip for the store default):",
        "stgy_no_reset": "♾ No reset",
        "stgy_day": "☀️ Daily",
        "stgy_week": "🗓 Weekly",
        "stgy_month": "📆 Monthly",
        "svc_field_strategy": "Traffic reset",
        "svc_field_hwid": "Devices",
        "svc_field_squad": "Squad",
        "svc_invalid_strategy": "❌ Invalid strategy. Use NO_RESET, DAY, WEEK or MONTH.",
        "hwid_default": "Panel default (Unlimited)",
        "hwid_zero": "Disabled",
        "svc_devices": "{n} devices",
        "skip_for_none": "Send /skip to clear this value.",
        # --- quick renewal from alerts ---
        "btn_renew_account": "🔄 Renew this account",
        "buy_for_account_toast": "Renewing account: {username}",
        # --- maintenance mode ---
        "maintenance_user": (
            "🛠 <b>The bot is under maintenance.</b>\n\n"
            "Purchases are temporarily disabled. Please try again later."
        ),
        "btn_maintenance": "🚧 Maintenance mode: {state}",
        "settings_maintenance": "Maintenance",
        "maint_toggled": "Maintenance mode: {state}",
        # --- dashboard ---
        "btn_dashboard": "📊 Dashboard",
        "dash_title": "📊 <b>Dashboard</b>",
        "dash_users_total": "Total users",
        "dash_online": "Online now",
        "dash_verified": "Verified",
        "dash_new_today": "New today",
        "dash_new_week": "this week",
        "dash_revenue_today": "Revenue today",
        "dash_revenue_week": "Revenue 7d",
        "dash_topups_pending": "Pending top-ups",
        "dash_services_active": "Active services",
        # --- orders / refunds ---
        "ord_title": "Order",
        "ord_status": "Status",
        "ord_status_paid": "Paid",
        "ord_status_refunded": "Refunded",
        "btn_refund": "↩️ Refund to wallet",
        "ord_refund_confirm": (
            "↩️ <b>Refund order #{id}?</b>\n\n"
            "📦 {name}\n💰 {amount} Toman will be returned to the user's wallet."
        ),
        "ord_refunded": "✅ Refunded: <b>{amount}</b> Toman (user balance: {balance})",
        "refund_notice_user": (
            "↩️ Order #{id} was refunded. "
            "<b>{amount}</b> Toman has been returned to your wallet."
        ),
        # --- admin action log ---
        "btn_admin_logs": "📜 Action Log",
        "logs_title": "📜 <b>Admin action log</b>",
        "logs_empty": "No actions recorded yet.",
        "log_balance_add": "➕ Balance added",
        "log_balance_sub": "➖ Balance deducted",
        "log_refund": "↩️ Order refunded",
        "log_topup_ok": "✅ Top-up approved",
        "log_topup_no": "❌ Top-up rejected",
        "log_setting": "⚙️ Setting changed",
        "log_maintenance": "🚧 Maintenance toggled",
        "log_broadcast": "📢 Broadcast sent",
        # --- profile / my orders ---
        "profile_title": "👤 <b>My Account</b>",
        "profile_status": "Login status",
        "profile_status_verified": "✅ Verified",
        "profile_status_unverified": "❌ Not verified",
        "orders_count": "Orders",
        "profile_member_since": "Member since",
        "btn_my_orders": "🧾 My Orders",
        "orders_title": "🧾 <b>My Orders</b>",
        "orders_empty": "You have no orders yet.",
        # --- support ---
        "support_prompt": (
            "🎧 <b>Support</b>\n\n"
            "Send your question or problem in a single message.\n"
            "We will reply here as soon as possible."
        ),
        "support_sent": (
            "✅ <b>Your message was sent to support.</b>\n\n"
            "The reply will appear in this chat."
        ),
        "support_failed": (
            "❌ Could not deliver your message. Please try again later."
        ),
        "support_admin_header": (
            "💬 <b>New support message</b>\n"
            "👤 {name}\n"
            "🆔 <code>{tid}</code>\n"
            "🔗 {username}"
        ),
        "support_reply_header": "📨 <b>Support reply:</b>",
        # --- «درخواست سرویس جدید» free-text request (welcome screen) ---
        "request_prompt": (
            "🛒 <b>Request a new service</b>\n\n"
            "Describe what you need in a single message\n"
            "(e.g. volume, duration, number of devices).\n"
            "Our team will contact you shortly."
        ),
        "request_sent": (
            "✅ <b>Your request has been sent.</b>\n\n"
            "Our team will contact you as soon as possible."
        ),
        "request_admin_header": (
            "🛒 <b>New service request</b>\n"
            "👤 {name}\n"
            "🆔 <code>{tid}</code>\n"
            "🔗 {username}"
        ),
        "btn_request_done": "✅ Service created — notify user",
        "request_done_user": (
            "✅ <b>Your service has been created!</b>\n\n"
            "Open the bot and tap «Login» to access your account."
        ),
        "request_done_admin": "✅ The user has been notified.",
        "request_done_already": "The user was already notified.",
        # --- admin panel: users ---
        "btn_manage_users": "👥 Manage Users",
        "btn_prev": "⬅️ Prev",
        "btn_next": "Next ➡️",
        "page_info": "Page {page} / {pages}",
        "users_menu_title": "👥 <b>Users management</b>",
        "users_menu_hint": "Add a user or browse the user list:",
        "btn_user_list": "📋 User List",
        "btn_add_user": "➕ Add User",
        "btn_user_search": "🔍 Search User",
        "user_list_title": "📋 <b>User List</b>",
        "user_filter_all": "🌐 All",
        "user_filter_online": "🟢 Online",
        "user_filter_verified": "✅ Verified",
        "user_filter_unverified": "❌ Unverified",
        "user_add_prompt": "🆔 Send the user's numeric Telegram ID:",
        "user_add_invalid": "❌ Invalid ID. Please send a plain number.",
        "user_search_prompt": "🔍 Send Telegram ID or @username to search:",
        "user_search_empty": "No matching users found.",
        "user_add_created": "✅ User registered successfully.",
        "user_add_exists": "ℹ️ This user already exists.",
        "users_empty": "No users in this category.",
        "user_detail_title": "👤 <b>User</b>",
        "user_balance": "Balance",
        "user_panel_accounts": "Panel accounts",
        "user_last_active": "Last active",
        "btn_add_balance": "➕ Add balance",
        "btn_sub_balance": "➖ Deduct balance",
        "user_balance_prompt": "💰 Send the amount in Toman:",
        "user_balance_invalid": "❌ Invalid number. Please send a plain number.",
        "user_balance_ok": "✅ Balance updated: <b>{balance}</b> Toman",
        # --- admin panel: sales ---
        "btn_sales_report": "📑 Reports",
        "sales_title": "📈 <b>Sales & Orders Report</b>",
        "reports_hub_title": "📑 <b>Reports & System Monitoring</b>",
        "sales_total": "Total revenue",
        "sales_count": "Total orders",
        "sales_recent": "Orders list",
        "sales_empty": "No sales yet.",
        "ord_filter_all": "🔘 All ({n})",
        "ord_filter_paid": "✅ Paid ({n})",
        "ord_filter_pending": "⏳ Pending ({n})",
        "ord_filter_failed": "❌ Failed ({n})",
        "ord_filter_refunded": "🔄 Refunded ({n})",
        "btn_order_search": "🔍 Search Orders",
        "btn_order_clear_search": "❌ Clear Search",
        "ord_search_prompt": "🔍 <b>Enter Order ID, Telegram ID, or Panel Username:</b>",
        "ord_search_active": "🔍 <b>Search query:</b> <code>{query}</code>",
        "ord_active_filter": "🎯 <b>Active filter:</b> {filter} ({count} orders)",
        "ord_page_info": "📄 Page {page} of {pages}",
        "ord_empty_filtered": "No orders found matching this filter.",
        "btn_copy_config": "📋 Copy Config",
        # --- admin panel: top-ups ---
        "btn_topups": "💳 Approve Top-ups",
        "topups_title": "💳 <b>Pending top-ups</b>",
        "topups_empty": "No pending top-ups.",
        # --- admin panel: broadcast ---
        "btn_broadcast": "📢 Broadcast",
        "broadcast_prompt": "📝 Send the broadcast text:",
        "broadcast_preview": "👀 <b>Preview:</b>\n\n{text}",
        "btn_send": "📨 Send",
        "broadcast_sent": "✅ Sent: <b>{ok}</b> ok / <b>{fail}</b> failed",
        # --- admin panel: store settings ---
        "btn_store_settings": "⚙️ Store Settings",
        "store_settings_title": "⚙️ <b>Store Settings</b>",
        "settings_card": "Card number",
        "settings_holder": "Name",
        "settings_min": "Minimum top-up",
        "settings_value_prompt": "📝 Send the new value:",
        "settings_invalid_number": "❌ Invalid number. Please send a plain number.",
        "settings_squad": "Default Squad",
        "settings_grace_days": "Expiry Grace Period (days)",
        "settings_remind_days": "Expiry Reminder Days",
        "settings_support_contact": "Support Contact",
        "settings_topic_topups": "Top-ups Forum Topic ID",
        "settings_topic_orders": "Orders Forum Topic ID",
        "settings_topic_support": "Support Forum Topic ID",
        "settings_topic_alerts": "System Alerts Forum Topic ID",
        "settings_topics_btn": "🎧 Forum Topics Settings",
        "settings_topics_title": "🎧 <b>Admin Group Forum Topics Settings</b>",
        # --- admin user & panel management ---
        "btn_create_panel_user": "➕ Add User",
        "btn_panel_users_list": "👥 Users List",
        "user_filter_never": "⚪️ Never Connected",
        "user_filter_offline": "🔴 Offline",
        "user_filter_expiring": "⏳ Expiring Soon",
        "user_filter_limited": "⚠️ Limit Reached",
        "user_filter_disabled": "⛔️ Disabled",
        "user_create_prompt_username": "👤 <b>Enter username for the new panel account:</b>\n<i>(English letters and digits only, no spaces)</i>",
        "user_create_invalid_username": "❌ Invalid or duplicate username. Please enter alphanumeric characters only:",
        "user_create_prompt_traffic": "📊 <b>Enter traffic limit in Gigabytes (GB):</b>\n<i>(Enter 0 for unlimited traffic)</i>",
        "user_create_invalid_traffic": "❌ Please enter a valid number (in GB):",
        "user_create_prompt_duration": "📅 <b>Enter validity duration in days:</b>\n<i>(e.g., 30 for one month, or 0 for unlimited)</i>",
        "user_create_invalid_duration": "❌ Please enter a valid number of days:",
        "user_create_prompt_squad": "🧩 <b>Select Internal Squad for the account:</b>",
        "user_create_all_squads": "🌐 All Squads",
        "user_create_default_squad": "⚙️ Store Default",
        "user_create_prompt_hwid": "📱 <b>Select HWID Device Limit:</b>",
        "hwid_unlimited": "Unlimited",
        "hwid_n_devices": "{n} Device(s)",
        "user_create_prompt_telegram_id": "🆔 <b>Enter user's numeric Telegram ID (optional):</b>",
        "user_create_success": "✅ <b>Panel account created successfully!</b>\n\n👤 Username: <code>{username}</code>\n📊 Traffic: <b>{traffic}</b>\n📅 Duration: <b>{duration}</b>\n\n🔗 <b>Subscription URL:</b>\n<code>{sub_url}</code>",
        "user_create_error": "❌ Error creating account in Remnawave panel. Please check panel status.",
        "btn_edit_squads": "🧩 Edit Squads",
        "puser_squads_title": "🧩 <b>Manage User Squads</b>",
        "puser_squads_hint": "Tap a squad to toggle it on/off:",
        "toast_squads_updated": "✅ User squads updated.",
        "puser_title": "👤 <b>Panel User Management</b>",
        "puser_status_active": "🟢 Active",
        "puser_status_disabled": "⛔️ Disabled",
        "puser_status_limited": "⚠️ Limit Reached",
        "puser_status_expired": "⏳ Expired",
        "puser_status_never": "⚪️ Never Connected",
        "puser_status_online": "🟢 Online",
        "puser_status_offline": "🔴 Offline",
        "puser_traffic": "Traffic",
        "puser_expire": "Expiry",
        "puser_last_online": "Last Online",
        "puser_devices": "Devices (HWID)",
        "puser_sub_url": "Subscription URL",
        "btn_toggle_disable": "⛔️ Disable Account",
        "btn_toggle_enable": "🟢 Enable Account",
        "btn_reset_traffic": "🔄 Reset Traffic",
        "btn_revoke_sub": "🔗 Revoke & Change Link",
        "btn_view_devices": "📱 View Devices (HWID)",
        "btn_wallet_manage": "👛 Wallet Balance",
        "toast_traffic_reset": "✅ User traffic was successfully reset.",
        "toast_status_toggled": "✅ User status updated.",
        "toast_sub_revoked": "✅ New subscription link generated.",
        "puser_device_removed": "✅ Device removed.",
        "puser_no_devices": "No active devices recorded for this account.",
        # --- items 1 to 5: panel user management ---
        "btn_quick_extend": "➕ Extend / Add Traffic",
        "puser_extend_prompt_days": "📅 <b>Enter additional days to add:</b>\n<i>(Send 0 to keep current expiry date)</i>",
        "puser_extend_prompt_traffic": "📊 <b>Enter additional traffic in GB:</b>\n<i>(Send 0 to keep current traffic limit)</i>",
        "toast_user_extended": "✅ Service successfully extended.",
        "btn_traffic_strategy": "🔁 Strategy: {strategy}",
        "strat_title": "🔁 <b>Select Traffic Reset Strategy</b>",
        "strat_no_reset": "No Reset (Accumulate)",
        "strat_day": "Daily",
        "strat_week": "Weekly",
        "strat_month": "Monthly",
        "toast_strat_updated": "✅ Reset strategy updated.",
        "btn_hwid_limit": "📱 Device Limit: {limit}",
        "hwid_limit_title": "📱 <b>Select HWID Device Limit</b>",
        "toast_hwid_updated": "✅ Device limit updated.",
        "btn_edit_tid": "🆔 Telegram ID: {tid}",
        "puser_tid_prompt": "🆔 <b>Enter user's numeric Telegram ID:</b>\n<i>(Send 0 or /skip to remove Telegram link)</i>",
        "toast_tid_updated": "✅ Telegram ID updated.",
        "btn_edit_desc": "📝 Note: {desc}",
        "puser_desc_prompt": "📝 <b>Enter description or note for this account:</b>\n<i>(Send /skip to remove note)</i>",
        "toast_desc_updated": "✅ Account note updated.",
        # --- broadcast audience filters ---
        "bcast_target_title": "📢 <b>Broadcast Message</b>\n\n🎯 <i>Select target audience:</i>",
        "bcast_target_all": "👥 All Bot Users",
        "bcast_target_active": "🟢 Active Service Users",
        "bcast_target_expired": "⏳ Expired / No Service",
        "bcast_target_balance": "👛 Users with Balance",
        "bcast_target_buyers": "🛒 Previous Buyers",
        "bcast_preview_target": "🎯 <b>Target:</b> {target}\n👥 <b>Recipients:</b> {count} users\n\n{text}",
        # --- expiry lifecycle ---
        "expiry_reminder": (
            "⏰ <b>Your service expires in {days} days</b>\n\n"
            "👤 Account : <code>{username}</code>\n"
            "📅 Expiry : {date}\n\n"
            "Renew now to avoid disconnection 👇"
        ),
        "expiry_expired_grace": (
            "⚠️ <b>Your service has expired</b>\n\n"
            "👤 Account : <code>{username}</code>\n"
            "📅 Expired : {date}\n"
            "You have <b>{grace} days</b> of grace period left. "
            "Renew now to keep your connection 👇"
        ),
        "expiry_disabled": (
            "⛔️ <b>Your service was disabled</b>\n\n"
            "👤 Account : <code>{username}</code>\n"
            "The grace period is over. Renew to reactivate 👇"
        ),
        "btn_renew_now": "🔄 Renew now",
        # --- single configs ---
        "btn_single_configs": "🔌 Single Configs",
        "btn_get_configs": "🔌 Get Configs",
        "btn_back_to_configs": "🔙 Back to Configs List",
        "cfg_protocol": "Protocol",
        "configs_view_title": "🔌 <b>Config: {name}</b>",
        "configs_title": "🔌 <b>Account Configs</b>",
        "configs_desc": "Tap any config below to view and copy it:",
        "configs_pick_account": "Select which account you want to get configs for:",
        "configs_empty": "❌ <b>No configs found</b>\n\nUnable to load configs from subscription link. Please use the full subscription link in Account Management.",
        "configs_btn_all": "📋 Send All Configs",
        "configs_sent_toast": "✅ Config sent to chat",
        "configs_all_sent_toast": "✅ All configs sent to chat",
        "configs_item_header": "🔑 <b>Config: {name}</b>",
        "configs_copy_hint": "(Tap the box above to copy)",
        # --- account selection for purchase ---
        "btn_renew_account_item": "🔄 Renew: {username}",
        "btn_buy_new_account": "➕ Create New Account",
        "buy_choose_account_title": "Buy Service: {name}",
        "buy_choose_account_prompt": "Please choose which account this purchase is for:",
        "buy_target_account": "Target Account",
        "buy_target_new": "New Account",
        # --- digital receipt ---
        "receipt_title": "Digital Purchase Receipt",
        "receipt_date": "Date & Time",
        "receipt_status": "Payment Status",
        "receipt_status_paid": "Successful & Paid",
        "receipt_service": "Service Plan",
        "receipt_duration": "Duration",
        "receipt_traffic": "Traffic",
        "receipt_amount": "Amount Paid",
        "receipt_balance": "New Wallet Balance",
        "receipt_footer_hint": "Tap the subscription link above to copy, or tap «Get Configs» below to view individual configs.",
        "btn_copy_sub_link": "📋 Copy Subscription Link",
        # --- smart retention ---
        "retention_title": "We miss you!",
        "retention_body": "It has been {days} days since your service expired. To welcome you back, we have prepared a special 20% discount for you:",
        "retention_code_label": "Discount Code",
        "retention_cta": "Open the services menu now and renew your plan with discount! 🚀",
        # --- free trial ---
        "trial_already_claimed": "❌ You have already claimed your free trial account.",
        "trial_prompt_username": "🎁 <b>Free Trial Account ({traffic} GB - {days} Days)</b>\n\nPlease enter your desired username (English letters & digits, 3-20 chars):\nExample: <code>user123</code>",
        "trial_username_invalid": "⚠️ Invalid username. Use only English letters and digits (3-20 chars).",
        "trial_username_taken": "⚠️ This username is already registered. Please choose another.",
        "trial_receipt_title": "Free Trial Activation Receipt",
        "trial_welcome_hint": "Your trial is active! Use the main menu to check usage and manage settings.",
        # --- referral ---
        "btn_referral": "🤝 Invite Friends",
        "referral_title": "🤝 <b>Invite Friends & Earn Free Traffic</b>",
        "referral_body": "Share your referral link with friends. For every successful invite, earn <b>{reward_gb} GB free traffic</b>!\n\n🔗 <b>Your Invite Link (tap to copy):</b>\n<code>{link}</code>",
        "referral_stats": "👥 Successful invites: <b>{count}</b>\n🎁 Earned reward: <b>{total_gb}</b> GB",
        "btn_share_link": "📤 Share with Friends",
        "referral_reward_notify": "🎉 <b>Referral Reward!</b>\n\nA user joined using your invite link and <b>{reward_gb} GB</b> of free traffic was added to your account! 🎁",
        # --- coupons ---
        "btn_apply_coupon": "🏷 Apply Discount Code",
        "coupon_prompt": "🏷 <b>Enter your discount code:</b>",
        "coupon_applied": "✅ Discount code <b>{code}</b> applied! ({discount_text} discount)",
        "coupon_not_found": "❌ Invalid discount code.",
        "coupon_inactive": "❌ This discount code is currently inactive.",
        "coupon_expired": "❌ This discount code has expired.",
        "coupon_limit_reached": "❌ This discount code usage limit has been reached.",
        "coupon_already_used": "❌ You have already used this discount code.",
        "btn_coupons_admin": "🏷 Coupons",
        "coupons_admin_title": "🏷 <b>Coupons Management</b>",
        "btn_create_coupon": "➕ Create New Coupon",
        "coupon_created": "✅ Coupon <b>{code}</b> created successfully.",
        # --- ban / blacklist ---
        "btn_ban_user": "⛔️ Ban User",
        "btn_unban_user": "✅ Unban User",
        "user_banned_toast": "⛔️ User was banned successfully.",
        "user_unbanned_toast": "✅ User was unbanned successfully.",
        "btn_banned_list": "⛔️ Banned Users",
        "banned_list_title": "⛔️ <b>Banned Users List</b>",
        "banned_list_empty": "No banned users found.",
        "banned_user_notice": "⛔️ <b>Your account has been suspended.</b>\nPlease contact support.",
        # --- node monitor ---
        "btn_nodes_monitor": "🖥 Server Status",
        "nodes_title": "Server Status",
        # --- database backup ---
        "btn_backup_db": "💾 Database Backup",
        "backup_success": "✅ Database backup created successfully.",
        # --- settings labels ---
        "btn_settings_trial": "🎁 Trial Settings",
        "btn_settings_referral": "🤝 Invite Settings",
        "settings_trial_enabled": "Trial (1/0)",
        "settings_trial_traffic": "Trial Traffic (GB)",
        "settings_trial_duration": "Trial Duration (Days)",
        "settings_referral_enabled": "Invite System (1/0)",
        "settings_referral_reward": "Invite Reward (GB)",
    },
    "fa": {
        "welcome": (
            "👋 <b>خوش آمدید!</b>\n\n"
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:"
        ),
        "btn_login": "🔑 ورود",
        "btn_new_service": "🎁 سرویس تست",
        "btn_back": "🔙 بازگشت",
        "btn_back_to_menu": "🔙 منوی اصلی",
        "login_failed": (
            "❌ <b>ورود ناموفق</b>\n\n"
            "شناسه تلگرام شما در پنل یافت نشد.\n"
            "اگر هنوز اکانتی ندارید، به منوی قبل بازگردید و گزینه "
            "<b>درخواست سرویس جدید</b> را بزنید."
        ),
        "service_request_prompt": (
            "💬 <b>سلام! لطفاً پیام بگذارید، به‌زودی جواب می‌دهیم.</b>\n\n"
            "درخواست خود را در قالب یک پیام ارسال کنید:"
        ),
        "service_request_sent": (
            "✅ <b>پیام شما ارسال شد.</b>\n\n"
            "تیم ما در اسرع وقت با شما تماس خواهد گرفت."
        ),
        "main_menu_title": (
            "🏠 <b>منوی اصلی</b>\n\n"
            "یکی از بخش‌ها را انتخاب کنید:"
        ),
        "btn_quick_stats": "📊 آمار فوری",
        "btn_account_mgmt": "🛠 مدیریت اکانت",
        "btn_wallet": "👛 کیف پول",
        "btn_services": "📦 سرویس‌ها",
        "btn_connection_guide": "📚 آموزش اتصال",
        "btn_settings": "⚙️ تنظیمات",
        "btn_support": "\u200f🎧 پشتیبانی",
        "btn_profile": "👤 حساب کاربری",
        "btn_admin_panel": "🔐 پنل مدیریت",
        "section_placeholder": (
            "🚧 <b>{section}</b>\n\n"
            "این بخش در حال توسعه است."
        ),
        "not_authorized": "⛔️ شما اجازه دسترسی به این بخش را ندارید.",
        "not_verified": (
            "🚫 <b>شما احراز هویت نشده‌اید.</b>\n\n"
            "شناسه تلگرام شما در پنل یافت نشد.\n"
            "لطفاً ابتدا وارد شوید یا درخواست سرویس جدید ثبت کنید."
        ),
        "btn_refresh": "🔄 به‌روزرسانی",
        "stats_title": "⚡️ <b>آمار فوری</b>",
        "stats_account": "👤 اکانت",
        "stats_status": "📌 وضعیت",
        "stats_total": "📊 حجم کل",
        "stats_used": "🔥 حجم مصرف‌شده",
        "stats_remaining": "📥 حجم باقی‌مانده",
        "stats_unlimited": "♾ نامحدود",
        "stats_expire": "📅 انقضا",
        "stats_days_left": "{days} روز",
        "stats_expired_ago": "{days} روز پیش منقضی شده",
        "stats_no_expire": "♾ بدون انقضا",
        "stats_today": "⚡️ مجموع مصرف امروز",
        "stats_lifetime": "📈 مصرف کل از ابتدا",
        "stats_burn_rate": "⏳ با الگوی مصرف شما، حجم باقی‌مانده تا حدود <b>{days} روز</b> دیگر به پایان می‌رسد.",
        "stats_sparkline": "📊 روند ۷ روز اخیر : <code>{bars}</code> (<b>{total}</b>)",
        "stats_online_label": "📶 اتصال",
        "stats_online_now": "🟢",
        "stats_never_connected": "⚪️",
        "stats_multi_header": "🔗 <b>{count} اکانت</b> به تلگرام شما متصل است:",
        "stats_error": "⚠️ دریافت آمار از پنل ممکن نشد. لطفاً کمی بعد دوباره تلاش کنید.",
        "status_active": "✅",
        "status_disabled": "⛔️",
        "status_limited": "🚫",
        "status_expired": "⏰",
        # --- account management ---
        "acc_title": "🛠 <b>مدیریت اکانت</b>",
        "acc_pick": "یکی از اکانت‌ها را انتخاب کنید:",
        "acc_sub_link": "📥 لینک اشتراک (برای کپی لمس کنید):",
        "btn_open_sub": "🔗 باز کردن لینک",
        "btn_devices": "📱 دستگاه‌های متصل",
        "btn_revoke": "🔄 تعویض لینک",
        "btn_qr": "🧾 کد QR",
        "btn_close": "❌ بستن",
        "btn_cancel": "🔙 انصراف",
        "qr_caption": (
            "🧾 <b>کد QR لینک اشتراک</b>\n"
            "در اپ خود اسکن کنید تا اشتراک اضافه شود.\n\n"
            "<code>{link}</code>"
        ),
        "acc_error": "⚠️ عملیات انجام نشد. لطفاً کمی بعد دوباره تلاش کنید.",
        "devices_title": "📱 <b>دستگاه‌های متصل</b>",
        "devices_count": "🔢 تعداد دستگاه",
        "devices_empty": "هنوز دستگاهی روی این اکانت ثبت نشده است.",
        "device_last_seen": "🕓 آخرین اتصال",
        "device_ip": "🌍 آی‌پی",
        "btn_device_delete": "❌ حذف دستگاه {num}",
        "device_delete_confirm": (
            "❌ <b>این دستگاه حذف شود؟</b>\n\n"
            "{device}\n\n"
            "اتصال آن قطع و جای آن آزاد می‌شود. "
            "دستگاه با اولین اتصال دوباره ثبت خواهد شد."
        ),
        "btn_yes_delete": "✅ بله، حذف کن",
        "device_deleted": "✅ دستگاه حذف شد.",
        "device_new_connected": (
            "🔔 <b>اتصال دستگاه جدید به اکانت!</b>\n\n"
            "👤 اکانت : <code>{username}</code>\n"
            "📱 سیستم‌عامل : <b>{platform}</b>\n"
            "🏷 مدل دستگاه : <b>{model}</b>\n"
            "🌍 آی‌پی : <code>{ip}</code>\n\n"
            "⚠️ اگر این اتصال توسط شما نبوده، لطفاً دستگاه را از بخش مدیریت دستگاه‌ها بررسی یا حذف کنید."
        ),
        "revoke_confirm": (
            "🔄 <b>لینک اشتراک عوض شود؟</b>\n\n"
            "⚠️ لینک فعلی شما <b>بلافاصله از کار می‌افتد</b>.\n"
            "باید لینک جدید را دوباره در همه اپ‌های خود اضافه کنید.\n\n"
            "اگر لینک شما لو رفته یا دست کسی افتاده، از این گزینه استفاده کنید."
        ),
        "btn_yes_revoke": "✅ بله، عوض کن",
        "revoke_done": (
            "✅ <b>لینک اشتراک عوض شد!</b>\n\n"
            "لینک قبلی دیگر کار نمی‌کند. لینک جدید (برای کپی لمس کنید):"
        ),
        # --- connection guide ---
        "guide_title": "📚 <b>آموزش اتصال</b>",
        "guide_pick": "سیستم‌عامل خود را انتخاب کنید:",
        "guide_steps": (
            "1️⃣ یکی از اپ‌های زیر را نصب کنید.\n"
            "2️⃣ لینک اشتراک خود را کپی کنید (پایین همین پیام 👇).\n"
            "3️⃣ در اپ گزینه <b>افزودن اشتراک / Add Subscription</b> را بزنید.\n"
            "4️⃣ سرور دلخواه را انتخاب کرده و متصل شوید."
        ),
        "guide_your_link": "📥 لینک اشتراک شما (برای کپی لمس کنید):",
        "btn_platform_android": "🤖 اندروید",
        "btn_platform_ios": "🍏 آیفون",
        "btn_platform_windows": "🖥 ویندوز",
        "btn_platform_macos": "💻 مک",
        "btn_platform_linux": "🐧 لینوکس",
        # --- settings ---
        "settings_title": "⚙️ <b>تنظیمات</b>",
        "settings_traffic_label": "🔔 هشدار حجم",
        "settings_expire_label": "⏰ هشدار انقضا",
        "settings_traffic_hint": "وقتی مصرف شما از این درصد عبور کند پیام هشدار می‌گیرید.",
        "settings_expire_hint": "این تعداد روز مانده به انقضای سرویس پیام هشدار می‌گیرید.",
        "settings_percent_value": "{percent}%",
        "settings_days_value": "{days} روز",
        "alerts_off": "خاموش",
        "btn_set_traffic": "🔔 تغییر هشدار حجم",
        "btn_set_expire": "⏰ تغییر هشدار انقضا",
        "settings_pick_traffic": "وقتی مصرف از چند درصد گذشت خبر بدهیم؟",
        "settings_pick_expire": "چند روز قبل از انقضا خبر بدهیم؟",
        "settings_saved": "✅ ذخیره شد",
        # --- alerts ---
        "alert_traffic": (
            "⚠️ <b>هشدار حجم</b>\n\n"
            "👤 اکانت : <code>{username}</code>\n"
            "🔥 <b>{percent}%</b> از حجم شما مصرف شده است.\n"
            "📥 حجم باقی‌مانده : <b>{remaining}</b>\n\n"
            "برای جلوگیری از قطع شدن، همین حالا سرویس خود را تمدید یا ارتقا دهید 👇"
        ),
        "alert_expire": (
            "⏰ <b>هشدار انقضا</b>\n\n"
            "👤 اکانت : <code>{username}</code>\n"
            "📅 فقط <b>{days} روز</b> تا انقضای سرویس شما مانده است ({date}).\n\n"
            "برای جلوگیری از قطع شدن، همین حالا سرویس خود را تمدید کنید 👇"
        ),
        "alert_expire_now": (
            "⏰ <b>هشدار انقضا</b>\n\n"
            "👤 اکانت : <code>{username}</code>\n"
            "📅 سرویس شما <b>امروز منقضی می‌شود یا منقضی شده است</b> ({date}).\n\n"
            "برای اتصال دوباره، همین حالا سرویس خود را تمدید کنید 👇"
        ),
        # --- wallet ---
        "wallet_title": "👛 <b>کیف پول</b>",
        "wallet_balance": "💰 موجودی : <b>{balance} تومان</b>",
        "wallet_pending": "⏳ {count} درخواست شارژ در انتظار تایید دارید.",
        "btn_topup": "➕ شارژ کیف پول",
        "topup_amount_prompt": (
            "💳 <b>شارژ کیف پول</b>\n\n"
            "مبلغ مورد نظر خود را به تومان تایپ و ارسال کنید "
            "(حداقل {min} تومان)، یا یکی از مبالغ آماده زیر را انتخاب کنید:"
        ),
        "topup_amount_invalid": (
            "❌ مبلغ نامعتبر است. فقط یک عدد به تومان بفرستید (حداقل {min})."
        ),
        "topup_card_info": (
            "💳 مبلغ <b>{amount} تومان</b> را به کارت زیر واریز کنید:\n\n"
            "<code>{card}</code>\n"
            "👤 {holder}\n\n"
            "سپس <b>عکس رسید</b> (یا متن آن) را همین‌جا ارسال کنید."
        ),
        "topup_no_card": "⚠️ شارژ کیف پول فعلاً در دسترس نیست. با پشتیبانی تماس بگیرید.",
        "topup_receipt_registered": (
            "✅ <b>رسید شما ثبت شد.</b>\n\n"
            "بعد از تایید ادمین، کیف پول شما شارژ می‌شود و به شما اطلاع می‌دهیم."
        ),
        "topup_approved_user": (
            "✅ <b>شارژ {amount} تومانی شما تایید شد!</b>\n"
            "💰 موجودی جدید : <b>{balance} تومان</b>"
        ),
        "topup_rejected_user": (
            "❌ <b>رسید شارژ {amount} تومانی شما تایید نشد.</b>\n"
            "اگر فکر می‌کنید اشتباهی رخ داده، با پشتیبانی تماس بگیرید."
        ),
        "admin_topup_request": (
            "💳 <b>درخواست شارژ کیف پول</b> #{id}\n\n"
            "👤 {name}\n"
            "🆔 <code>{tid}</code>\n"
            "🔗 {username}\n"
            "💰 مبلغ : <b>{amount} تومان</b>\n\n"
            "⬆️ رسید، پیام بالاست."
        ),
        "btn_approve": "✅ تایید",
        "btn_reject": "❌ رد",
        "admin_topup_done": "✅ تایید شد — کیف پول شارژ شد.",
        "admin_topup_rejected": "❌ رد شد.",
        "admin_topup_already": "قبلاً بررسی شده است.",
        "topup_pending_limit": (
            "⏳ شما ۳ درخواست شارژ در انتظار دارید. "
            "لطفاً تا بررسی ادمین صبر کنید."
        ),
        "topup_receipt_invalid": (
            "❌ رسید نامعتبر است. عکس (حداکثر ۱۰ مگ) یا PDF بفرستید."
        ),
        "topup_duplicate_receipt": (
            "⚠️ این رسید قبلاً ثبت شده است. "
            "لطفاً رسید جدید بفرستید یا منتظر بررسی بمانید."
        ),
        "topups_history_title": "🧾 <b>گردش حساب و تاریخچه تراکنش‌ها</b>",
        "topups_history_empty": "هنوز تراکنشی در حساب شما ثبت نشده است.",
        "btn_topup_history": "🧾 تاریخچه شارژ",
        "topup_status_pending": "⏳ در انتظار",
        "topup_status_approved": "✅ تاییدشده",
        "topup_status_rejected": "❌ ردشده",
        "tx_topup": "شارژ کیف پول",
        "tx_topup_pending": "درخواست شارژ (در انتظار)",
        "tx_topup_rejected": "درخواست شارژ (ردشده)",
        "tx_order_paid": "خرید/تمدید سرویس",
        "tx_order_refunded": "برگشت وجه به کیف پول",
        "btn_language": "🌐 زبان",
        # --- reports ---
        "nightly_title": "🌙 <b>گزارش شبانه</b>",
        "weekly_title": "📊 <b>گزارش هفتگی</b>",
        "weekly_day": "▪️ در {date} : <b>{total}</b>",
        "weekly_others": "سایر",
        "weekly_total": "📊 مصرف کل این هفته : <b>{total}</b>",
        "weekly_hi": "سلام {name} 👋",
        "weekly_sum_total": "این هفته <b>{total}</b> مصرف داشتی.",
        "weekly_sum_more": "این مصرف {percent}% بیشتر از هفته قبل بود.",
        "weekly_sum_less": "این مصرف {percent}% کمتر از هفته قبل بود.",
        "weekly_sum_same": "تقریباً برابر با هفته قبل.",
        "weekly_sum_top": (
            "پرمصرف‌ترین روزت <b>{day}</b> بود و بیشتر از سرور "
            "{flag} <b>{node}</b> استفاده کردی."
        ),
        "monthly_title": "🗓 <b>گزارش ماهانه — {month}</b>",
        "monthly_day": "▪️ در {date} : <b>{total}</b>",
        "monthly_others": "سایر",
        "monthly_total": "📊 مصرف کل این ماه : <b>{total}</b>",
        "monthly_hi": "سلام {name} 👋",
        "monthly_sum_total": "این ماه ({month}) مقدار <b>{total}</b> مصرف داشتی.",
        "monthly_sum_more": "این مصرف {percent}% بیشتر از ماه قبل بود.",
        "monthly_sum_less": "این مصرف {percent}% کمتر از ماه قبل بود.",
        "monthly_sum_same": "تقریباً برابر با ماه قبل.",
        "monthly_sum_top": (
            "پرمصرف‌ترین روزت <b>{day}</b> بود و بیشتر از سرور "
            "{flag} <b>{node}</b> استفاده کردی."
        ),
        "report_used_breakdown": "🔥 حجم مصرف‌شده (به تفکیک سرور) :",
        "report_today_breakdown": "⚡️ مصرف امروز :",
        "settings_nightly_label": "🌙 گزارش شبانه",
        "settings_weekly_label": "📊 گزارش هفتگی",
        "settings_nightly_hint": "هر شب ساعت ۲۳:۵۹ خلاصه مصرف برایتان ارسال می‌شود.",
        "settings_weekly_hint": "جمعه‌شب‌ها ساعت ۲۳:۵۹ گزارش کامل هفته ارسال می‌شود.",
        "settings_monthly_label": "🗓 گزارش ماهانه",
        "settings_monthly_hint": "آخرین روز ماه شمسی ساعت ۲۳:۵۹ گزارش کامل ماه ارسال می‌شود.",
        "toggle_on": "روشن",
        "toggle_off": "خاموش",
        "btn_toggle_nightly": "🌙 گزارش شبانه: {state}",
        "btn_toggle_weekly": "📊 گزارش هفتگی: {state}",
        "btn_toggle_monthly": "🗓 گزارش ماهانه: {state}",
        # --- services ---
        "services_title": "📦 <b>سرویس‌ها</b>",
        "services_active_empty": "در حال حاضر سرویسی موجود نیست. کمی بعد دوباره تلاش کنید.",
        "btn_request": "📨 درخواست این سرویس",
        "svc_view_title": "📦 <b>{name}</b>",
        "svc_request_sent": (
            "✅ <b>درخواست شما ثبت شد.</b>\n\n"
            "تیم ما در اسرع وقت با شما تماس خواهد گرفت."
        ),
        "svc_field_name": "نام",
        "svc_field_price": "قیمت",
        "svc_field_duration": "مدت",
        "svc_field_traffic": "ترافیک",
        "svc_field_description": "توضیح",
        "svc_currency": "تومان",
        "unlimited": "♾ نامحدود",
        "svc_days": "{days} روز",
        "svc_gb": "{gb} گیگابایت",
        "services_policy_hint": (
            "💡 <b>نکته دوره‌های مصرف و تمدید:</b>\n"
            "در سرویس‌های با ریست ترافیک «<b>♾️ بدون ریست</b>»، چنانچه تا <b>۱ روز</b> "
            "پس از منقضی شدن سرویس اقدام به تمدید نمایید، باقیمانده حجم به دوره بعد منتقل خواهد شد. "
            "برای سایر حالت‌ها (روزانه، هفتگی و ماهانه)، حجم در هر دوره ریست می‌شود."
        ),
        # --- admin panel / services management ---
        "admin_panel_title": "🔐 <b>پنل مدیریت</b>",
        "admin_panel_hint": "از اینجا سرویس‌ها و تنظیمات دیگر را مدیریت کنید.",
        "btn_manage_services": "📦 مدیریت سرویس‌ها",
        "admin_services_title": "📦 <b>مدیریت سرویس‌ها</b>",
        "services_empty": "هنوز سرویسی ندارید. از پایین اضافه کنید 👇",
        "btn_add_service": "➕ افزودن سرویس",
        "btn_edit": "✏️ ویرایش",
        "btn_delete": "🗑 حذف",
        "btn_enable": "✅ فعال",
        "btn_disable": "⛔️ غیرفعال",
        "svc_state_active": "✅ فعال",
        "svc_state_inactive": "⛔️ غیرفعال",
        "svc_prompt_name": "🏷 <b>نام</b> سرویس را بفرستید:",
        "svc_prompt_price": "💰 <b>قیمت</b> را به تومان بفرستید:",
        "svc_prompt_duration": "📅 <b>مدت</b> را به روز بفرستید (0 = نامحدود):",
        "svc_prompt_traffic": "📊 <b>ترافیک</b> را به گیگابایت بفرستید (0 = نامحدود):",
        "svc_prompt_description": "📝 یک <b>توضیح</b> کوتاه بفرستید (یا /skip):",
        "svc_invalid_number": "❌ عدد نامعتبر است. فقط یک عدد بفرستید.",
        "svc_invalid_name": "❌ نام نمی‌تواند خالی باشد.",
        "svc_created": "✅ سرویس ساخته شد: <b>{name}</b>",
        "svc_updated": "✅ سرویس به‌روزرسانی شد: <b>{name}</b>",
        "svc_deleted": "🗑 سرویس حذف شد: <b>{name}</b>",
        "svc_delete_confirm": "🗑 <b>این سرویس حذف شود؟</b>\n\n<b>{name}</b>",
        "svc_edit_title": "✏️ <b>ویرایش سرویس</b> — یک فیلد را انتخاب کنید:",
        "svc_requested_admin_title": "درخواست سرویس جدید",
        "svc_requested_user": "کاربر",
        "svc_requested_username": "یوزرنیم",
        # --- automatic purchase ---
        "btn_buy": "🛒 خرید",
        "btn_confirm_pay": "✅ پرداخت و فعال‌سازی",
        "buy_confirm_title": "🧾 <b>تایید خرید</b>",
        "buy_current_balance": "موجودی فعلی",
        "buy_insufficient": (
            "❌ <b>موجودی کافی نیست.</b>\n\n"
            "💰 قیمت : <b>{price}</b> {currency}\n"
            "👛 موجودی شما : <b>{balance}</b> {currency}\n\n"
            "لطفاً ابتدا کیف پول خود را شارژ کنید."
        ),
        "buy_choose_account": (
            "🤔 <b>شما بیش از یک اکانت دارید.</b>\n\n"
            "کدام‌یک را تمدید کنیم؟"
        ),
        "buy_success": "خرید موفق",
        "buy_success_link": (
            "🔗 <b>لینک اشتراک:</b>\n"
            "<code>{url}</code>\n\n"
            "این لینک در بخش «مدیریت اکانت» هم موجود است."
        ),
        "buy_remaining_balance": "👛 موجودی باقی‌مانده : <b>{balance}</b> {currency}",
        "buy_failed": (
            "❌ <b>فعال‌سازی انجام نشد.</b>\n\n"
            "هیچ مبلغی کسر نشده است. لطفاً دوباره تلاش کنید."
        ),
        "buy_admin_log": "خرید جدید",
        # --- service extras: strategy / hwid / squad ---
        "svc_prompt_strategy": "🔁 استراتژی ریست ترافیک را انتخاب کنید:",
        "svc_prompt_hwid": "📱 سقف تعداد دستگاه متصل را وارد کنید (یا /skip برای پیش‌فرض پنل - نامحدود):",
        "svc_prompt_squad": "🧩 اسکواد داخلی (UUID) را بفرستید (یا /skip برای پیش‌فرض فروشگاه):",
        "stgy_no_reset": "♾ بدون ریست",
        "stgy_day": "☀️ روزانه",
        "stgy_week": "🗓 هفتگی",
        "stgy_month": "📆 ماهانه",
        "svc_field_strategy": "ریست ترافیک",
        "svc_field_hwid": "دستگاه",
        "svc_field_squad": "اسکواد",
        "svc_invalid_strategy": "❌ مقدار نامعتبر. از NO_RESET، DAY، WEEK یا MONTH استفاده کنید.",
        "hwid_default": "پیش‌فرض پنل (نامحدود)",
        "hwid_zero": "غیرفعال",
        "svc_devices": "{n} دستگاه",
        "skip_for_none": "برای خالی‌کردن این مقدار /skip بفرستید.",
        # --- quick renewal from alerts ---
        "btn_renew_account": "🔄 تمدید این اکانت",
        "buy_for_account_toast": "تمدید اکانت: {username}",
        # --- maintenance mode ---
        "maintenance_user": (
            "🛠 <b>ربات در حال بروزرسانی است.</b>\n\n"
            "خرید موقتاً غیرفعال است. لطفاً کمی بعد دوباره تلاش کنید."
        ),
        "btn_maintenance": "🚧 حالت تعمیر: {state}",
        "settings_maintenance": "حالت تعمیر",
        "maint_toggled": "حالت تعمیر: {state}",
        # --- dashboard ---
        "btn_dashboard": "📊 داشبورد",
        "dash_title": "📊 <b>داشبورد</b>",
        "dash_users_total": "کل کاربران",
        "dash_online": "آنلاین الان",
        "dash_verified": "تاییدشده",
        "dash_new_today": "جدید امروز",
        "dash_new_week": "این هفته",
        "dash_revenue_today": "درآمد امروز",
        "dash_revenue_week": "درآمد ۷ روز",
        "dash_topups_pending": "شارژهای در انتظار",
        "dash_services_active": "سرویس‌های فعال",
        # --- orders / refunds ---
        "ord_title": "سفارش",
        "ord_status": "وضعیت",
        "ord_status_paid": "پرداخت‌شده",
        "ord_status_refunded": "بازگشت‌خورده",
        "btn_refund": "↩️ بازگشت وجه به کیف پول",
        "ord_refund_confirm": (
            "↩️ <b>سفارش #{id} بازگشت داده شود؟</b>\n\n"
            "📦 {name}\n💰 مبلغ <b>{amount}</b> تومان به کیف پول کاربر برمی‌گردد."
        ),
        "ord_refunded": "✅ بازگشت داده شد: <b>{amount}</b> تومان (موجودی کاربر: {balance})",
        "refund_notice_user": (
            "↩️ سفارش #{id} لغو و مبلغ <b>{amount}</b> تومان به کیف پول شما برگردانده شد."
        ),
        # --- admin action log ---
        "btn_admin_logs": "📜 لاگ اقدامات",
        "logs_title": "📜 <b>لاگ اقدامات ادمین</b>",
        "logs_empty": "هنوز اقدامی ثبت نشده است.",
        "log_balance_add": "➕ افزایش موجودی",
        "log_balance_sub": "➖ کاهش موجودی",
        "log_refund": "↩️ بازگشت وجه سفارش",
        "log_topup_ok": "✅ تایید شارژ",
        "log_topup_no": "❌ رد شارژ",
        "log_setting": "⚙️ تغییر تنظیمات",
        "log_maintenance": "🚧 تغییر حالت تعمیر",
        "log_broadcast": "📢 ارسال پیام همگانی",
        # --- profile / my orders ---
        "profile_title": "👤 <b>حساب کاربری</b>",
        "profile_status": "وضعیت ورود",
        "profile_status_verified": "✅ وارد شده",
        "profile_status_unverified": "❌ وارد نشده",
        "orders_count": "تعداد سفارش‌ها",
        "profile_member_since": "عضو از",
        "btn_my_orders": "🧾 سفارش‌های من",
        "orders_title": "🧾 <b>سفارش‌های من</b>",
        "orders_empty": "هنوز سفارشی ثبت نکرده‌اید.",
        # --- support ---
        "support_prompt": (
            "🎧 <b>پشتیبانی</b>\n\n"
            "سوال یا مشکل خود را در یک پیام بفرستید.\n"
            "پاسخ در همین چت به شما اعلام می‌شود."
        ),
        "support_sent": (
            "✅ <b>پیام شما برای پشتیبانی ارسال شد.</b>\n\n"
            "پاسخ در همین چت نمایش داده می‌شود."
        ),
        "support_failed": (
            "❌ ارسال پیام انجام نشد. لطفاً کمی بعد دوباره تلاش کنید."
        ),
        "support_admin_header": (
            "💬 <b>پیام جدید پشتیبانی</b>\n"
            "👤 {name}\n"
            "🆔 <code>{tid}</code>\n"
            "🔗 {username}"
        ),
        "support_reply_header": "📨 <b>پاسخ پشتیبانی:</b>",
        # --- «درخواست سرویس جدید» free-text request (welcome screen) ---
        "request_prompt": (
            "🛒 <b>درخواست سرویس جدید</b>\n\n"
            "درخواست خود را در یک پیام بنویسید\n"
            "(مثلاً حجم، مدت، تعداد دستگاه).\n"
            "تیم ما در اسرع وقت با شما تماس می‌گیرد."
        ),
        "request_sent": (
            "✅ <b>درخواست شما ثبت شد.</b>\n\n"
            "تیم ما در اسرع وقت با شما تماس خواهد گرفت."
        ),
        "request_admin_header": (
            "🛒 <b>درخواست سرویس جدید</b>\n"
            "👤 {name}\n"
            "🆔 <code>{tid}</code>\n"
            "🔗 {username}"
        ),
        # --- admin panel: users ---
        "btn_manage_users": "👥 مدیریت کاربران",
        "btn_prev": "⬅️ قبلی",
        "btn_next": "بعدی ➡️",
        "page_info": "صفحه {page} / {pages}",
        "users_menu_title": "👥 <b>مدیریت کاربران</b>",
        "users_menu_hint": "افزودن کاربر یا مشاهده لیست کاربران:",
        "btn_user_list": "📋 لیست کاربران",
        "btn_add_user": "➕ افزودن کاربر",
        "btn_user_search": "🔍 جستجوی کاربر",
        "user_list_title": "📋 <b>لیست کاربران</b>",
        "user_filter_all": "🌐 همه",
        "user_filter_online": "🟢 آنلاین",
        "user_filter_verified": "✅ تاییدشده",
        "user_filter_unverified": "❌ تاییدنشده",
        "user_add_prompt": "🆔 آیدی عددی تلگرام کاربر را بفرستید:",
        "user_add_invalid": "❌ آیدی نامعتبر است. فقط یک عدد بفرستید.",
        "user_search_prompt": "🔍 آیدی عددی یا @یوزرنیم را برای جستجو بفرستید:",
        "user_search_empty": "کاربری پیدا نشد.",
        "user_add_created": "✅ کاربر با موفقیت ثبت شد.",
        "user_add_exists": "ℹ️ این کاربر از قبل وجود دارد.",
        "users_empty": "کاربری در این دسته وجود ندارد.",
        "user_detail_title": "👤 <b>کاربر</b>",
        "user_balance": "موجودی",
        "user_panel_accounts": "اکانت‌های پنل",
        "user_last_active": "آخرین فعالیت",
        "btn_add_balance": "➕ افزایش موجودی",
        "btn_sub_balance": "➖ کاهش موجودی",
        "user_balance_prompt": "💰 مبلغ را به تومان بفرستید:",
        "user_balance_invalid": "❌ عدد نامعتبر است. فقط یک عدد بفرستید.",
        "user_balance_ok": "✅ موجودی به‌روزرسانی شد: <b>{balance}</b> تومان",
        # --- admin panel: sales ---
        "btn_sales_report": "📑 گزارش",
        "sales_title": "📈 <b>گزارش و لیست سفارشات</b>",
        "reports_hub_title": "📑 <b>مرکز گزارشات و مانیتورینگ</b>",
        "sales_total": "مجموع درآمد",
        "sales_count": "کل سفارشات",
        "sales_recent": "لیست سفارشات",
        "sales_empty": "هنوز سفارشی ثبت نشده است.",
        "ord_filter_all": "🔘 همه ({n})",
        "ord_filter_paid": "✅ موفق ({n})",
        "ord_filter_pending": "⏳ در انتظار ({n})",
        "ord_filter_failed": "❌ ناموفق ({n})",
        "ord_filter_refunded": "🔄 مرجوعی ({n})",
        "btn_order_search": "🔍 جستجوی سفارش",
        "btn_order_clear_search": "❌ پاک‌کردن جستجو",
        "ord_search_prompt": "🔍 <b>شناسه سفارش، شناسه عددی تلگرام، یا نام کاربری پنل را ارسال کنید:</b>",
        "ord_search_active": "🔍 <b>عبارت جستجو:</b> <code>{query}</code>",
        "ord_active_filter": "🎯 <b>فیلتر فعال:</b> {filter} ({count} سفارش)",
        "ord_page_info": "📄 صفحه {page} از {pages}",
        "ord_empty_filtered": "هیچ سفارشی با این مشخصات یافت نشد.",
        "btn_copy_config": "📋 کپی کانفیگ",
        # --- admin panel: top-ups ---
        "btn_topups": "💳 تایید شارژها",
        "topups_title": "💳 <b>شارژهای در انتظار</b>",
        "topups_empty": "شارژ در انتظاری وجود ندارد.",
        # --- admin panel: broadcast ---
        "btn_broadcast": "📢 پیام همگانی",
        "broadcast_prompt": "📝 متن پیام همگانی را بفرستید:",
        "broadcast_preview": "👀 <b>پیش‌نمایش:</b>\n\n{text}",
        "btn_send": "📨 ارسال",
        "broadcast_sent": "✅ ارسال شد: <b>{ok}</b> موفق / <b>{fail}</b> ناموفق",
        # --- admin panel: store settings ---
        "btn_store_settings": "⚙️ تنظیمات فروشگاه",
        "store_settings_title": "⚙️ <b>تنظیمات فروشگاه</b>",
        "settings_card": "شماره کارت",
        "settings_holder": "نام",
        "settings_min": "حداقل مبلغ شارژ",
        "settings_value_prompt": "📝 مقدار جدید را بفرستید:",
        "settings_invalid_number": "❌ عدد نامعتبر است. فقط یک عدد بفرستید.",
        "settings_squad": "اسکواد پیش‌فرض",
        "settings_grace_days": "مهلت پس از انقضا (روز)",
        "settings_remind_days": "روزهای هشدار انقضا",
        "settings_support_contact": "آیدی پشتیبانی",
        "settings_topic_topups": "تاپیک تایید شارژها",
        "settings_topic_orders": "تاپیک ثبت سفارشات",
        "settings_topic_support": "تاپیک پیام‌های پشتیبانی",
        "settings_topic_alerts": "تاپیک هشدارهای سیستم",
        "settings_topics_btn": "\u200f🎧 تنظیمات تاپیک‌ها",
        "settings_topics_title": "🎧 <b>تنظیمات تاپیک‌های گروه مدیریت</b>",
        # --- admin user & panel management ---
        "btn_create_panel_user": "➕ افزودن کاربر",
        "btn_panel_users_list": "👥 لیست کاربران",
        "user_filter_never": "⚪️ هرگز متصل نشده",
        "user_filter_offline": "🔴 آفلاین",
        "user_filter_expiring": "⏳ در آستانه انقضا",
        "user_filter_limited": "⚠️ پایان حجم",
        "user_filter_disabled": "⛔️ غیرفعال",
        "user_create_prompt_username": "👤 <b>نام کاربری (Username) اکانت جدید پنل را وارد کنید:</b>\n(فقط حروف انگلیسی و اعداد - بدون فاصله)",
        "user_create_invalid_username": "❌ نام کاربری نامعتبر است یا از قبل وجود دارد. لطفاً یک نام انگلیسی بدون فاصله وارد کنید:",
        "user_create_prompt_traffic": "📊 <b>میزان حجم مجاز را به گیگابایت (GB) وارد کنید:</b>\n(برای حجم نامحدود عدد 0 را وارد کنید)",
        "user_create_invalid_traffic": "❌ لطفاً یک عدد معتبر (به گیگابایت) وارد کنید:",
        "user_create_prompt_duration": "📅 <b>مدت اعتبار اکانت را به روز وارد کنید:</b>\n(مثلاً 30 برای یک ماه، یا 0 برای نامحدود)",
        "user_create_invalid_duration": "❌ لطفاً تعداد روز را به صورت عدد وارد کنید:",
        "user_create_prompt_squad": "🧩 <b>اسکواد داخلی (Internal Squad) اکانت را انتخاب کنید:</b>",
        "user_create_all_squads": "🌐 همه اسکوادها",
        "user_create_default_squad": "⚙️ پیش‌فرض فروشگاه",
        "user_create_prompt_hwid": "📱 <b>محدودیت تعداد دستگاه‌های مجاز (HWID Device Limit):</b>",
        "hwid_unlimited": "نامحدود",
        "hwid_n_devices": "{n} دستگاه",
        "user_create_prompt_telegram_id": "🆔 <b>شناسه عددی تلگرام کاربر را وارد کنید (اختیاری):</b>",
        "user_create_success": "✅ <b>اکانت پنل با موفقیت ایجاد شد!</b>\n\n👤 نام کاربری: <code>{username}</code>\n📊 حجم: <b>{traffic}</b>\n📅 اعتبار: <b>{duration}</b>\n\n🔗 <b>لینک سابسکریپشن:</b>\n<code>{sub_url}</code>",
        "user_create_error": "❌ خطا در ایجاد اکانت در پنل رمنویو. لطفاً وضعیت پنل را بررسی کنید.",
        "btn_edit_squads": "🧩 تغییر اسکوادها",
        "puser_squads_title": "🧩 <b>تنظیم اسکوادهای کاربر</b>",
        "puser_squads_hint": "روی هر اسکواد بزنید تا فعال یا غیرفعال شود:",
        "toast_squads_updated": "✅ اسکوادهای کاربر با موفقیت تغییر کرد.",
        "puser_title": "👤 <b>مدیریت کاربر پنل</b>",
        "puser_status_active": "🟢 فعال",
        "puser_status_disabled": "⛔️ غیرفعال",
        "puser_status_limited": "⚠️ پایان حجم",
        "puser_status_expired": "⏳ منقضی شده",
        "puser_status_never": "⚪️ هرگز متصل نشده",
        "puser_status_online": "🟢 آنلاین",
        "puser_status_offline": "🔴 آفلاین",
        "puser_traffic": "حجم مصرفی",
        "puser_expire": "تاریخ انقضا",
        "puser_last_online": "آخرین اتصال",
        "puser_devices": "دستگاه‌های متصل",
        "puser_sub_url": "لینک اشتراک",
        "btn_toggle_disable": "⛔️ غیرفعال‌سازی",
        "btn_toggle_enable": "🟢 فعال‌سازی",
        "btn_reset_traffic": "🔄 صفر کردن مصرف",
        "btn_revoke_sub": "🔗 تغییر لینک اشتراک",
        "btn_view_devices": "📱 دستگاه‌های متصل (HWID)",
        "btn_wallet_manage": "👛 مدیریت موجودی کیف پول",
        "toast_traffic_reset": "✅ حجم مصرفی کاربر با موفقیت صفر شد.",
        "toast_status_toggled": "✅ وضعیت کاربر با موفقیت تغییر کرد.",
        "toast_sub_revoked": "✅ لینک اشتراک جدید با موفقیت صادر شد.",
        "puser_device_removed": "✅ دستگاه با موفقیت حذف شد.",
        "puser_no_devices": "دستگاه فعالی برای این اکانت ثبت نشده است.",
        # --- items 1 to 5: panel user management ---
        "btn_quick_extend": "➕ تمدید / افزایش حجم",
        "puser_extend_prompt_days": "📅 <b>تعداد روزهای تمدید را وارد کنید:</b>\n(برای عدم تغییر تاریخ انقضا عدد 0 را بفرستید)",
        "puser_extend_prompt_traffic": "📊 <b>میزان حجم افزوده‌شده را به گیگابایت (GB) وارد کنید:</b>\n(برای عدم تغییر حجم مجاز عدد 0 را بفرستید)",
        "toast_user_extended": "✅ سرویس کاربر با موفقیت تمدید شد.",
        "btn_traffic_strategy": "🔁 دوره ریست: {strategy}",
        "strat_title": "🔁 <b>انتخاب دوره ریست ترافیک</b>",
        "strat_no_reset": "بدون ریست (تجمعی)",
        "strat_day": "روزانه",
        "strat_week": "هفتگی",
        "strat_month": "ماهانه",
        "toast_strat_updated": "✅ دوره ریست ترافیک به‌روزرسانی شد.",
        "btn_hwid_limit": "📱 سقف دستگاه: {limit}",
        "hwid_limit_title": "📱 <b>تنظیم سقف اتصال همزمان دستگاه‌ها</b>",
        "toast_hwid_updated": "✅ سقف دستگاه‌های مجاز به‌روزرسانی شد.",
        "btn_edit_tid": "🆔 شناسه تلگرام: {tid}",
        "puser_tid_prompt": "🆔 <b>شناسه عددی تلگرام کاربر را وارد کنید:</b>\n(برای حذف اتصال تلگرام عدد 0 یا /skip را ارسال کنید)",
        "toast_tid_updated": "✅ شناسه تلگرام کاربر با موفقیت ثبت شد.",
        "btn_edit_desc": "📝 یادداشت: {desc}",
        "puser_desc_prompt": "📝 <b>متن یادداشت یا توضیحات برای این اکانت را وارد کنید:</b>\n(برای حذف یادداشت عبارت /skip را ارسال کنید)",
        "toast_desc_updated": "✅ یادداشت کاربر با موفقیت ذخیره شد.",
        # --- broadcast audience filters ---
        "bcast_target_title": "📢 <b>ارسال پیام همگانی</b>\n\n🎯 مخاطبان هدف پیام را انتخاب کنید:",
        "bcast_target_all": "👥 همه کاربران ربات",
        "bcast_target_active": "🟢 کاربران دارای سرویس فعال",
        "bcast_target_expired": "⏳ منقضی‌شده / بدون سرویس",
        "bcast_target_balance": "👛 دارای موجودی کیف پول",
        "bcast_target_buyers": "🛒 خریداران قبلی سرویس",
        "bcast_preview_target": "🎯 <b>مخاطب هدف:</b> {target}\n👥 <b>تعداد دریافت‌کنندگان:</b> {count} کاربر\n\n{text}",
        # --- expiry lifecycle ---
        "expiry_reminder": (
            "⏰ <b>{days} روز تا انقضای سرویس مانده</b>\n\n"
            "👤 اکانت : <code>{username}</code>\n"
            "📅 انقضا : {date}\n\n"
            "برای جلوگیری از قطعی همین حالا تمدید کنید 👇"
        ),
        "expiry_expired_grace": (
            "⚠️ <b>سرویس شما منقضی شده</b>\n\n"
            "👤 اکانت : <code>{username}</code>\n"
            "📅 انقضا : {date}\n"
            "<b>{grace} روز</b> مهلت (grace) دارید. "
            "برای حفظ اتصال تمدید کنید 👇"
        ),
        "expiry_disabled": (
            "⛔️ <b>سرویس شما غیرفعال شد</b>\n\n"
            "👤 اکانت : <code>{username}</code>\n"
            "مهلت تمام شد. برای فعال‌سازی مجدد تمدید کنید 👇"
        ),
        "btn_renew_now": "🔄 تمدید",
        # --- single configs ---
        "btn_single_configs": "🔌 دریافت کانفیگ تکی",
        "btn_get_configs": "🔌 دریافت کانفیگ",
        "btn_back_to_configs": "🔙 بازگشت به لیست کانفیگ‌ها",
        "cfg_protocol": "پروتکل",
        "configs_view_title": "🔌 <b>کانفیگ: {name}</b>",
        "configs_title": "🔌 <b>کانفیگ‌های اکانت</b>",
        "configs_desc": "برای مشاهده و کپی هر کانفیگ، روی آن کلیک کنید:",
        "configs_pick_account": "اکانتی که می‌خواهید کانفیگ‌های آن را دریافت کنید انتخاب کنید:",
        "configs_empty": "❌ <b>کانفیگی یافت نشد</b>\n\nامکان دریافت کانفیگ‌ها از لینک اشتراک فراهم نشد. لطفاً از لینک اشتراک کامل در مدیریت اکانت استفاده کنید.",
        "configs_btn_all": "📋 ارسال همه کانفیگ‌ها",
        "configs_sent_toast": "✅ کانفیگ به چت ارسال شد",
        "configs_all_sent_toast": "✅ تمام کانفیگ‌ها ارسال شدند",
        "configs_item_header": "🔑 <b>کانفیگ: {name}</b>",
        "configs_copy_hint": "(برای کپی کردن، روی کادر بالا لمس کنید)",
        # --- account selection for purchase ---
        "btn_renew_account_item": "🔄 تمدید: {username}",
        "btn_buy_new_account": "➕ ساخت اکانت جدید",
        "buy_choose_account_title": "خرید سرویس: {name}",
        "buy_choose_account_prompt": "لطفاً مشخص کنید این خرید برای کدام اکانت اعمال شود:",
        "buy_target_account": "اکانت مقصد",
        "buy_target_new": "ساخت اکانت جدید",
        # --- digital receipt ---
        "receipt_title": "رسید دیجیتال خرید سرویس",
        "receipt_date": "تاریخ و ساعت",
        "receipt_status": "وضعیت پرداخت",
        "receipt_status_paid": "موفق و پرداخت‌شده",
        "receipt_service": "پلن سرویس",
        "receipt_duration": "مدت اعتبار",
        "receipt_traffic": "حجم ترافیک",
        "receipt_amount": "مبلغ پرداخت‌شده",
        "receipt_balance": "موجودی جدید کیف پول",
        "receipt_footer_hint": "برای کپی، روی لینک بالا لمس کنید یا برای دریافت کانفیگ‌های مجزا، دکمه «دریافت کانفیگ» را بزنید.",
        "btn_copy_sub_link": "📋 کپی لینک اتصال",
        # --- smart retention ---
        "retention_title": "دلتنگ شما هستیم!",
        "retention_body": "{days} روز از تاریخ انقضای سرویس شما گذشته است. برای همراهی مجدد و تمدید سرویس، یک تخفیف ۲۰ درصدی ویژه برای شما در نظر گرفته‌ایم:",
        "retention_code_label": "کد تخفیف",
        "retention_cta": "همین حالا وارد منوی سرویس‌ها شوید و پلن مورد نظر خود را با تخفیف تمدید کنید! 🚀",
        # --- free trial ---
        "trial_already_claimed": "❌ شما قبلاً از سهمیه سرویس تست استفاده کرده‌اید.",
        "trial_prompt_username": "🎁 <b>دریافت سرویس تست ({traffic} گیگابایت - {days} روز)</b>\n\nلطفاً یک نام کاربری دلخواه (فقط حروف و اعداد انگلیسی، بین ۳ تا ۲۰ کاراکتر) ارسال کنید:\nمثال: <code>user123</code>",
        "trial_username_invalid": "⚠️ نام کاربری نامعتبر است. فقط از حروف و اعداد انگلیسی استفاده کنید (۳ تا ۲۰ کاراکتر).",
        "trial_username_taken": "⚠️ این نام کاربری قبلاً در پنل ثبت شده است. لطفاً نام دیگری انتخاب کنید.",
        "trial_receipt_title": "رسید فعال‌سازی سرویس تست",
        "trial_welcome_hint": "سرویس تست شما فعال شد! از منوی اصلی می‌توانید وضعیت مصرف و تنظیمات را مدیریت کنید.",
        # --- referral ---
        "btn_referral": "🤝 دعوت از دوستان",
        "referral_title": "🤝 <b>دعوت از دوستان و دریافت اینترنت رایگان</b>",
        "referral_body": "با ارسال لینک اختصاصی خود به دوستانتان، به ازای هر دعوت موفق، <b>{reward_gb} گیگابایت ترافیک هدیه</b> دریافت کنید!\n\n🔗 <b>لینک دعوت اختصاصی شما (برای کپی لمس کنید):</b>\n<code>{link}</code>",
        "referral_stats": "👥 تعداد دعوت‌های موفق: <b>{count}</b> نفر\n🎁 ترافیک هدیه دریافت‌شده: <b>{total_gb}</b> گیگابایت",
        "btn_share_link": "📤 اشتراک‌گذاری با دوستان",
        "referral_reward_notify": "🎉 <b>پاداش دعوت از دوستان!</b>\n\nکاربری با لینک دعوت شما به ربات پیوست و <b>{reward_gb} گیگابایت</b> ترافیک رایگان به اکانت شما اضافه شد! 🎁",
        # --- coupons ---
        "btn_apply_coupon": "🏷 اعمال کد تخفیف",
        "coupon_prompt": "🏷 <b>کد تخفیف خود را ارسال کنید:</b>",
        "coupon_applied": "✅ کد تخفیف <b>{code}</b> اعمال شد! ({discount_text} تخفیف)",
        "coupon_not_found": "❌ کد تخفیف واردشده معتبر نیست.",
        "coupon_inactive": "❌ این کد تخفیف در حال حاضر غیرفعال است.",
        "coupon_expired": "❌ مهلت استفاده از این کد تخفیف به پایان رسیده است.",
        "coupon_limit_reached": "❌ ظرفیت استفاده از این کد تخفیف تکمیل شده است.",
        "coupon_already_used": "❌ شما قبلاً از این کد تخفیف استفاده کرده‌اید.",
        "btn_coupons_admin": "🏷 کدهای تخفیف",
        "coupons_admin_title": "🏷 <b>مدیریت کدهای تخفیف</b>",
        "btn_create_coupon": "➕ ایجاد کد تخفیف جدید",
        "coupon_created": "✅ کد تخفیف <b>{code}</b> با موفقیت ایجاد شد.",
        # --- ban / blacklist ---
        "btn_ban_user": "⛔️ مسدودسازی کاربر",
        "btn_unban_user": "✅ رفع مسدودیت کاربر",
        "user_banned_toast": "⛔️ کاربر با موفقیت مسدود شد.",
        "user_unbanned_toast": "✅ مسدودیت کاربر رفع شد.",
        "btn_banned_list": "⛔️ لیست مسدودی",
        "banned_list_title": "⛔️ <b>لیست مسدودی</b>",
        "banned_list_empty": "هیچ کاربری در لیست مسدودی وجود ندارد.",
        "banned_user_notice": "⛔️ <b>حساب کاربری شما مسدود شده است.</b>\nجهت پیگیری با پشتیبانی در ارتباط باشید.",
        # --- node monitor ---
        "btn_nodes_monitor": "🖥 وضعیت سرور",
        "nodes_title": "وضعیت سرور",
        # --- database backup ---
        "btn_backup_db": "💾 پشتیبان‌گیری دیتابیس",
        "backup_success": "✅ نسخه پشتیبان از دیتابیس با موفقیت ایجاد شد.",
        # --- settings labels ---
        "btn_settings_trial": "🎁 تنظیمات تست",
        "btn_settings_referral": "🤝 تنظیمات دعوت",
        "settings_trial_enabled": "تست (1/0)",
        "settings_trial_traffic": "حجم تست (GB)",
        "settings_trial_duration": "مدت تست (روز)",
        "settings_referral_enabled": "سیستم دعوت (1/0)",
        "settings_referral_reward": "پاداش دعوت (GB)",
    },
}

DEFAULT_LANG = "fa"


def t(lang: str | None, key: str, **kwargs) -> str:
    """Translate a key for the given language with optional formatting."""
    lang = lang if lang in TEXTS else DEFAULT_LANG
    text = TEXTS[lang].get(key, key)
    return text.format(**kwargs) if kwargs else text
