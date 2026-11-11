"""Iranian Bank SMS Parser Engine.

Parses deposit SMS notifications from Iranian banks (Mellat, Melli, Pasargad,
Tejarat, Saderat, Saman, BluBank, Vepod, Sepah, Mehr, Resalat, Keshavarzi, etc.)
and extracts deposit amount (normalized to Tomans and Rials), bank name, and card/account info.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Persian/Arabic digit to English translation table
_DIGIT_MAP = str.maketrans({
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
})

# Withdrawal or non-deposit keywords that indicate the SMS is NOT an incoming credit
_WITHDRAWAL_KEYWORDS = (
    "برداشت",
    "خرید",
    "انتقال از حساب",
    "انتقال از کارت",
    "انتقال از سپرده",
    "انتقال کارت به کارت",
    "انتقال به دیگری",
    "انتقال به کارت دیگری",
    "انتقال به حساب دیگری",
    "انتقال به سپرده دیگری",
    "انتقال وجه",
    "انتقال پایا",
    "انتقال ساتنا",
    "کاهش موجودی",
    "بدهکار شد",
    "بدهکار",
    "رمز پویا",
    "رمز یکبار مصرف",
    "رمز موقت",
    "کارمزد",
    "تسویه",
    "چک برگشتی",
    "کسر شد",
    "ناموفق",
    "برگشت",
    "برگشتی",
    "لغو",
    "خطا",
    "عدم موفقیت",
    "برگشت داده شد",
    "برگشت به حساب",
    "از حساب شما پرید",
)

_OTP_KEYWORDS = ("رمز پویا", "رمز یکبار مصرف", "رمز موقت")
_FAILED_KEYWORDS = (
    "ناموفق",
    "برگشت",
    "برگشتی",
    "لغو",
    "خطا",
    "عدم موفقیت",
    "برگشت داده شد",
    "برگشت به حساب",
)

# Deposit keywords confirming an incoming transfer/credit
_DEPOSIT_KEYWORDS = (
    "واریز",
    "واریز شد",
    "واریز به",
    "بستانکار شد",
    "بستانکار",
    "واریز به کارت",
    "واریز به حساب",
    "واریز به سپرده",
    "به کارت شما",
    "به حساب شما",
    "به سپرده شما",
    "کارت به کارت به کارت",  # Bank Mellat incoming transfer pattern
    "افزایش موجودی",
    "به حساب شما نشست",
    "نشست",
)

# Known Iranian banks keywords in SMS sender or body, ordered by priority (specific banks first)
_BANK_NAMES: list[tuple[str, str]] = [
    ("blubank", "بلوبانک"),
    ("بلو", "بلوبانک"),
    ("به حساب شما نشست", "بلوبانک"),
    ("vepod", "ویپاد"),
    ("ویپاد", "ویپاد"),
    ("mellat", "بانک ملت"),
    ("ملت", "بانک ملت"),
    ("melli", "بانک ملی"),
    ("ملی", "بانک ملی"),
    ("pasargad", "بانک پاسارگاد"),
    ("پاسارگاد", "بانک پاسارگاد"),
    ("tejarat", "بانک تجارت"),
    ("تجارت", "بانک تجارت"),
    ("saderat", "بانک صادرات"),
    ("صادرات", "بانک صادرات"),
    ("saman", "بانک سامان"),
    ("سامان", "بانک سامان"),
    ("sepah", "بانک سپه"),
    ("سپه", "بانک سپه"),
    ("keshavarzi", "بانک کشاورزی"),
    ("کشاورزی", "بانک کشاورزی"),
    ("masken", "بانک مسکن"),
    ("مسکن", "بانک مسکن"),
    ("parsian", "بانک پارسیان"),
    ("پارسیان", "بانک پارسیان"),
    ("ayandeh", "بانک آینده"),
    ("آینده", "بانک آینده"),
    ("resalat", "بانک رسالت"),
    ("رسالت", "بانک رسالت"),
    ("mehr", "بانک مهر ایران"),
    ("مهر", "بانک مهر ایران"),
    ("shahr", "بانک شهر"),
    ("شهر", "بانک شهر"),
    ("refah", "بانک رفاه"),
    ("رفاه", "بانک رفاه"),
    ("sina", "بانک سینا"),
    ("سینا", "بانک سینا"),
]


@dataclass(slots=True)
class ParsedBankSms:
    is_deposit: bool
    amount_toman: int | None
    amount_rial: int | None
    bank_name: str | None
    card_last4: str | None
    tracking_code: str | None
    raw_text: str
    reject_reason: str | None = None


def _rejected_sms(raw_text: str, bank_name: str | None = None, reason: str = "") -> ParsedBankSms:
    return ParsedBankSms(
        is_deposit=False,
        amount_toman=None,
        amount_rial=None,
        bank_name=bank_name,
        card_last4=None,
        tracking_code=None,
        raw_text=raw_text,
        reject_reason=reason or None,
    )


def _classify_withdrawal_reason(norm_lower: str) -> str:
    if any(kw in norm_lower for kw in _OTP_KEYWORDS):
        return "پیامک رمز یکبار مصرف یا احراز هویت است"
    if any(kw in norm_lower for kw in _FAILED_KEYWORDS):
        return "تراکنش ناموفق یا برگشتی بوده است"
    return "تراکنش برداشت، خرید یا انتقال خروجی از حساب است"


def normalize_sms_digits(text: str) -> str:
    """Normalize Persian and Arabic digits and strip zero-width characters."""
    if not text:
        return ""
    cleaned = text.translate(_DIGIT_MAP)
    # Normalize Persian comma and arabic decimal/thousands separators
    cleaned = cleaned.replace("٬", ",").replace("٫", ".").replace("،", ",")
    # Remove zero-width spaces / non-joiners
    cleaned = cleaned.replace("\u200c", " ").replace("\u200b", "").replace("\ufeff", "")
    return cleaned


def detect_bank_name(text: str, sender: str = "") -> str | None:
    """Detect bank name from sender or message content."""
    combined = f"{sender} {text}".lower()
    for key, name in _BANK_NAMES:
        if key in combined:
            return name
    return None


def parse_bank_sms(text: str, sender: str = "") -> ParsedBankSms:
    """Parse an Iranian bank SMS message into structured data."""
    if not text or not text.strip():
        return _rejected_sms(text or "", reason="متن پیامک خالی است")

    norm_text = normalize_sms_digits(text)
    bank_name = detect_bank_name(norm_text, sender)

    # 1. Check for withdrawal keywords or negative amounts (e.g. 1,290,000-)
    norm_lower = norm_text.lower()
    if any(kw in norm_lower for kw in _WITHDRAWAL_KEYWORDS):
        return _rejected_sms(text, bank_name=bank_name, reason=_classify_withdrawal_reason(norm_lower))

    if re.search(r"(?:خرید|برداشت|مبلغ)\s*[:：]?\s*[\d,]{4,15}\s*\-(?!\d)|(?:^|[\s:])[\d,]{4,15}\s*\-(?!\d)", norm_lower):
        return _rejected_sms(text, bank_name=bank_name, reason="تراکنش برداشت یا کسر از حساب (علامت منفی) است")

    # Check for outgoing transfer without explicit deposit indicators (e.g. "انتقال به کارت ... مبلغ ... انجام شد")
    if (
        ("انتقال به کارت" in norm_lower or "انتقال به حساب" in norm_lower or "انتقال به سپرده" in norm_lower or "انتقال وجه" in norm_lower)
        and not ("شما" in norm_lower or "واریز" in norm_lower or "بستانکار" in norm_lower or "+" in norm_lower or "کارت به کارت به کارت" in norm_lower)
    ):
        return _rejected_sms(text, bank_name=bank_name, reason="تراکنش انتقال خروجی از حساب است")

    # 2. Check for deposit keywords (or explicit + amount notation, excluding phone numbers like +98912...)
    has_plus_deposit = bool(
        re.search(r"(?:[\d,]+\s*\+|\+\s*\d{1,3}(?:,\d{3})+|\+\s*[\d,]+\s*(?:ریال|تومان|ت|r|irr)\b)", norm_lower)
    )
    has_deposit = has_plus_deposit or any(kw in norm_lower for kw in _DEPOSIT_KEYWORDS)
    if not has_deposit:
        return _rejected_sms(
            text,
            bank_name=bank_name,
            reason="فاقد کلیدواژه واریز بانکی (پیامک تست وب‌هوک، تبلیغاتی یا اطلاع‌رسانی)",
        )

    # 3. Extract Card / Account Last 4 digits if present
    # Look for masked cards like 603799***4762 or 6280***4762 or account numbers ending with 4 digits
    card_last4 = None
    masked_card_match = re.search(r"[*xX\-]+(\d{4})\b", norm_text)
    if masked_card_match:
        card_last4 = masked_card_match.group(1)
    else:
        card_match = re.search(r"(?:کارت|حساب|سپرده|به)\s*[:：]?\s*(?:[*\d-]*?)(\d{4})\b", norm_text)
        if card_match:
            card_last4 = card_match.group(1)

    # 4. Extract Tracking / Reference Code if present (e.g. پیگیری: 123456 or ارجاع: 123456)
    tracking_code = None
    track_match = re.search(r"(?:پیگیری|ارجاع|شناسه|کد)\s*[:：]?\s*(\d{5,14})\b", norm_text)
    if track_match:
        tracking_code = track_match.group(1)

    # 5. Extract Amount
    # Common Patterns:
    # Pattern A: "مبلغ: 503,700 ریال" or "مبلغ 50,370 تومان" or "مبلغ: 503700R"
    # Pattern B: "واریز: 503,700 ریال" or "واریز 50,370 تومان" or "+503,700 ریال" or "کارت700,000+"
    # Pattern C: "50,370 تومان واریز شد" or "11,421,100ریال به حساب شما نشست"
    amount_toman = None
    amount_rial = None
    has_explicit_unit = False

    patterns = [
        # Explicit "مبلغ: 559,370 ریال" or "واریز: 559,370 ریال"
        r"(?:مبلغ|واریز|بستانکار)\s*[:：]?\s*([\d,]{3,15})\s*(ریال|تومان|ت|R|IRR)?",
        # Refah / Keshavarzi plus notation: "کارت700,000+" or "700,000+"
        r"(?:کارت|حساب|سپرده|واریز)?\s*([\d,]{4,15})\s*\+",
        # "+700,000 ریال" or "+700,000"
        r"\+\s*([\d,]{3,15})\s*(ریال|تومان|ت|R|IRR)?",
        # "559,370 ریال واریز شد" or "11,421,100ریال به حساب شما نشست"
        r"([\d,]{3,15})\s*(ریال|تومان)\s*(?:واریز|به حساب|به کارت|نشست)",
        # Any number immediately followed by ریال or تومان
        r"([\d,]{3,15})\s*(ریال|تومان)",
    ]

    for pat in patterns:
        for match in re.finditer(pat, norm_text, re.IGNORECASE):
            # Ignore balance numbers ("مانده: ..." / "موجودی: ...")
            prefix_ctx = norm_text[max(0, match.start() - 18) : match.start()]
            if re.search(r"(?:مانده|موجودی)\s*[:：]?\s*$", prefix_ctx):
                continue

            raw_num = match.group(1) if match.lastindex >= 1 else ""
            unit = match.group(2) if match.lastindex >= 2 and match.group(2) else ""

            clean_digits = re.sub(r"[^\d]", "", raw_num)
            if not clean_digits:
                continue

            val = int(clean_digits)
            # Filter out short IDs/year fragments < 1000
            if val < 1000:
                continue

            unit_lower = unit.lower()
            if "تومان" in unit_lower or unit_lower == "ت":
                amount_toman = val
                amount_rial = val * 10
                has_explicit_unit = True
                break
            elif "ریال" in unit_lower or unit_lower in ("r", "irr"):
                amount_rial = val
                amount_toman = val // 10
                has_explicit_unit = True
                break
            elif "+" in raw_num or "+" in match.group(0):
                # Require comma-grouping for unitless leading + amounts to avoid phone numbers (+98912...)
                if match.group(0).lstrip().startswith("+") and "," not in raw_num:
                    continue
                amount_rial = val
                amount_toman = val // 10
                has_explicit_unit = True
                break
            else:
                # Disallow guessing currency units; continue scanning later matches in the SMS
                continue
        if amount_toman is not None:
            break

    is_valid_deposit = bool(amount_toman is not None and amount_toman > 0 and has_explicit_unit)
    reject_reason = None if is_valid_deposit else "کلیدواژه واریز یافت شد اما مبلغ یا واحد پول معتبر (ریال/تومان) در متن تشخیص داده نشد"

    return ParsedBankSms(
        is_deposit=is_valid_deposit,
        amount_toman=amount_toman if is_valid_deposit else None,
        amount_rial=amount_rial if is_valid_deposit else None,
        bank_name=bank_name,
        card_last4=card_last4,
        tracking_code=tracking_code,
        raw_text=text,
        reject_reason=reject_reason,
    )
