"""Persian translations dictionary."""

FA_TEXTS: dict[str, str] = {
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
        "btn_connection_guide": "📚 آموزش",
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
        "guide_title": "📚 <b>آموزش</b>",
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
            "💳 <b>درخواست شارژ کیف پول</b> (فیش {id})\n\n"
            "👤 {name}\n"
            "🆔 <code>{tid}</code>\n"
            "🔗 {username}\n"
            "💰 مبلغ : <b>{amount} تومان</b>"
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
        "weekly_day": "📅 {day} {date} : <b>{total}</b>",
        "weekly_others": "سایر",
        "weekly_total": "📊 مصرف کل این هفته : <b>{total}</b>",
        "weekly_hi": "سلام {name} 👋",
        "weekly_sum_total": "این هفته <b>{total}</b> مصرف داشتی.",
        "weekly_sum_more": "این مصرف {percent}% بیشتر از هفته قبل بود.",
        "weekly_sum_less": "این مصرف {percent}% کمتر از هفته قبل بود.",
        "weekly_sum_same": "تقریباً برابر با هفته قبل.",
        "weekly_sum_top": (
            "پرمصرف‌ترین روزت <b>{day}</b> بود و بیشترین مصرفت روی {flag} بود."
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
        "settings_clean_reports_label": "🧹 پاکسازی گزارش‌های قبلی",
        "settings_clean_reports_hint": "قبل از ارسال گزارش جدید، گزارش قبلی در چت حذف می‌شود تا صفحه شلوغ نشود.",
        "settings_wheel_notify_label": "🎡 یادآور گردونه شانس",
        "settings_wheel_notify_hint": "به محض اتمام ۲۴ ساعت و شارژ مجدد گردونه، پیام یادآوری ارسال می‌شود.",
        "toggle_on": "روشن",
        "toggle_off": "خاموش",
        "btn_toggle_nightly": "🌙 گزارش شبانه {state}",
        "btn_toggle_weekly": "📊 گزارش هفتگی {state}",
        "btn_toggle_monthly": "🗓 گزارش ماهانه {state}",
        "btn_toggle_clean_reports": "🧹 پاکسازی قبلی {state}",
        "btn_toggle_wheel_notify": "🎡 یادآور گردونه {state}",
        "wheel_ready_notify": (
            "🎡 <b>گردونه شانس آماده چرخش است!</b>\n\n"
            "هم‌اکنون شانس روزانه شما شارژ شده و می‌توانید با چرخاندن گردونه در مینی‌اپ، "
            "جوایز ویژه (حجم، اعتبار یا تخفیف) دریافت کنید 👇"
        ),
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
        "svc_gb": "{gb} GB",
        "services_policy_hint": (
            "💡 <b>نکته دوره‌های مصرف و تمدید:</b>\n"
            "در سرویس‌های با ریست ترافیک «<b>بدون ریست</b>»، چنانچه تا <b>۱ روز</b> "
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
        "svc_state_active": "✅",
        "svc_state_inactive": "❌",
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
        "svc_prompt_hwid": "📱 سقف تعداد دستگاه متصل را وارد کنید (یا /skip برای پیش‌فرض - نامحدود):",
        "svc_prompt_squad": "🧩 اسکواد داخلی (UUID) را بفرستید (یا /skip برای پیش‌فرض فروشگاه):",
        "stgy_no_reset": "بدون ریست",
        "stgy_day": "☀️ روزانه",
        "stgy_week": "🗓 هفتگی",
        "stgy_month": "📆 ماهانه",
        "svc_field_strategy": "ریست ترافیک",
        "svc_field_hwid": "دستگاه",
        "svc_field_squad": "اسکواد",
        "svc_invalid_strategy": "❌ مقدار نامعتبر. از NO_RESET، DAY، WEEK یا MONTH استفاده کنید.",
        "hwid_default": "پیش‌فرض (نامحدود)",
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
        "btn_store_settings": "⚙️ تنظیمات",
        "store_settings_title": "⚙️ <b>تنظیمات</b>",
        "settings_card": "شماره کارت",
        "settings_holder": "نام",
        "settings_min": "حداقل مبلغ شارژ",
        "settings_value_prompt": "📝 مقدار جدید را بفرستید:",
        "settings_invalid_number": "❌ عدد نامعتبر است. فقط یک عدد بفرستید.",
        "settings_squad": "اسکواد",
        "settings_grace_days": "مهلت پس از انقضا",
        "settings_remind_days": "روزهای هشدار انقضا",
        "settings_support_contact": "آیدی پشتیبانی",
        "settings_topic_topups": "تاپیک تایید شارژها",
        "settings_topic_orders": "تاپیک ثبت سفارشات",
        "settings_topic_support": "تاپیک پیام‌های پشتیبانی",
        "settings_topic_alerts": "تاپیک هشدارهای سیستم",
        "settings_topic_crypto": "تاپیک کریپتو و نرخ ارز",
        "settings_topic_errors": "تاپیک لاگ‌های ارور",
        "settings_ton_wallet": "آدرس والت TON",
        "settings_ton_rate": "نرخ هر تون (تومان)",
        "settings_usdt_rate": "نرخ مبنای تتر (تومان)",
        "btn_topup_card": "💳 کارت به کارت (فیش بانکی)",
        "btn_topup_ton": "💎 پرداخت با تون (آنلاین و آنی)",
        "topup_select_method": "👛 <b>انتخاب روش شارژ کیف پول</b>\n\nلطفاً روش افزایش موجودی مورد نظر خود را انتخاب کنید:",
        "settings_topics_btn": "🎧 تاپیک‌ها",
        "settings_topics_title": "🎧 <b>تاپیک‌ها</b>",
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
        "receipt_status_paid": "موفق",
        "receipt_service": "نام سرویس",
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
        "btn_backup_db": "💾 پشتیبان‌گیری",
        "backup_success": "✅ نسخه پشتیبان از دیتابیس با موفقیت ایجاد شد.",
        # --- settings labels ---
        "btn_settings_trial": "🎁 تنظیمات تست",
        "btn_settings_referral": "🤝 تنظیمات دعوت",
        "settings_trial_enabled": "تست (1/0)",
        "settings_trial_traffic": "حجم (GB)",
        "settings_trial_duration": "زمان (روز)",
        "settings_referral_enabled": "سیستم دعوت (1/0)",
        "settings_referral_reward": "حجم (GB)",
}
