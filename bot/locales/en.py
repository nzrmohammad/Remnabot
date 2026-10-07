"""English translations dictionary."""

EN_TEXTS: dict[str, str] = {
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
        "btn_connection_guide": "📚 Guide",
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
        "guide_title": "📚 <b>Guide</b>",
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
            "💳 <b>Wallet top-up request</b> (Receipt {id})\n\n"
            "👤 {name}\n"
            "🆔 <code>{tid}</code>\n"
            "🔗 {username}\n"
            "💰 Amount : <b>{amount} Toman</b>"
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
        "weekly_day": "📅 {day} {date} : <b>{total}</b>",
        "weekly_others": "others",
        "weekly_total": "📊 Total this week : <b>{total}</b>",
        "weekly_hi": "Hi {name} 👋",
        "weekly_sum_total": "You used <b>{total}</b> this week.",
        "weekly_sum_more": "That's {percent}% more than last week.",
        "weekly_sum_less": "That's {percent}% less than last week.",
        "weekly_sum_same": "About the same as last week.",
        "weekly_sum_top": (
            "Your busiest day was <b>{day}</b> and you mostly used {flag}."
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
        "btn_toggle_nightly": "🌙 Nightly report {state}",
        "btn_toggle_weekly": "📊 Weekly report {state}",
        "btn_toggle_monthly": "🗓 Monthly report {state}",
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
            "For plans with '<b>No Reset</b>' strategy, renewing within <b>1 day</b> "
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
        "svc_state_active": "✅",
        "svc_state_inactive": "❌",
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
        "svc_prompt_hwid": "📱 Send max device limit (or /skip for default - Unlimited):",
        "svc_prompt_squad": "🧩 Send the internal squad UUID (or /skip for the store default):",
        "stgy_no_reset": "No reset",
        "stgy_day": "☀️ Daily",
        "stgy_week": "🗓 Weekly",
        "stgy_month": "📆 Monthly",
        "svc_field_strategy": "Traffic reset",
        "svc_field_hwid": "Devices",
        "svc_field_squad": "Squad",
        "svc_invalid_strategy": "❌ Invalid strategy. Use NO_RESET, DAY, WEEK or MONTH.",
        "hwid_default": "Default (Unlimited)",
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
        "btn_store_settings": "⚙️ Settings",
        "store_settings_title": "⚙️ <b>Settings</b>",
        "settings_card": "Card number",
        "settings_holder": "Name",
        "settings_min": "Minimum top-up",
        "settings_value_prompt": "📝 Send the new value:",
        "settings_invalid_number": "❌ Invalid number. Please send a plain number.",
        "settings_squad": "Squad",
        "settings_grace_days": "Expiry Grace Period",
        "settings_remind_days": "Expiry Reminder Days",
        "settings_support_contact": "Support Contact",
        "settings_topic_topups": "Top-ups Forum Topic ID",
        "settings_topic_orders": "Orders Forum Topic ID",
        "settings_topic_support": "Support Forum Topic ID",
        "settings_topic_alerts": "System Alerts Forum Topic ID",
        "settings_topic_crypto": "Crypto & Rates Forum Topic ID",
        "settings_topic_errors": "Error Logs Forum Topic ID",
        "settings_ton_wallet": "TON Wallet Address",
        "settings_ton_rate": "TON Exchange Rate (Toman)",
        "settings_usdt_rate": "Benchmark USDT Rate (Toman)",
        "btn_topup_card": "💳 Card-to-Card",
        "btn_topup_ton": "💎 Pay with TON",
        "topup_select_method": "👛 <b>Select Top-up Method:</b>\n\nChoose your preferred payment method to add balance to your wallet:",
        "settings_topics_btn": "🎧 Topics",
        "settings_topics_title": "🎧 <b>Topics</b>",
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
        "receipt_status_paid": "Successful",
        "receipt_service": "Service Name",
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
        "btn_backup_db": "💾 Backup",
        "backup_success": "✅ Database backup created successfully.",
        # --- settings labels ---
        "btn_settings_trial": "🎁 Trial Settings",
        "btn_settings_referral": "🤝 Invite Settings",
        "settings_trial_enabled": "Trial (1/0)",
        "settings_trial_traffic": "Traffic (GB)",
        "settings_trial_duration": "Duration (Days)",
        "settings_referral_enabled": "Invite System (1/0)",
        "settings_referral_reward": "Traffic (GB)",
}
