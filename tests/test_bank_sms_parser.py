"""Unit tests for Iranian Bank SMS Parser."""
import pytest
from bot.services.payment.bank_sms_parser import parse_bank_sms, normalize_sms_digits


def test_normalize_sms_digits():
    raw = "واریز ۵۵۹,۳۷۰ ریال به کارت ۶۲۸۰"
    norm = normalize_sms_digits(raw)
    assert norm == "واریز 559,370 ریال به کارت 6280"


def test_parse_mellat_sms():
    sms = """بانک ملت
واریز به حساب: 12345678
مبلغ: 559,370 ریال
موجودی: 12,500,000 ریال
1403/08/07-14:35"""
    res = parse_bank_sms(sms, sender="+98200033")
    assert res.is_deposit is True
    assert res.amount_toman == 55937
    assert res.amount_rial == 559370
    assert res.bank_name == "بانک ملت"


def test_parse_melli_persian_digits():
    sms = """بانک ملی ایران
واریز به ۶۰۳۷۹۹******۴۷۶۲
مبلغ: ۵۵۹,۳۷۰ ریال
مانده: ۱,۴۲۰,۰۰۰ ریال
پیگیری: ۹۸۷۶۵۴۳۲۱"""
    res = parse_bank_sms(sms)
    assert res.is_deposit is True
    assert res.amount_toman == 55937
    assert res.amount_rial == 559370
    assert res.bank_name == "بانک ملی"
    assert res.card_last4 == "4762"
    assert res.tracking_code == "987654321"


def test_parse_blubank_toman():
    sms = """بلوبانک
واریز 55,937 تومان
از علی احمدی
به حساب شما"""
    res = parse_bank_sms(sms)
    assert res.is_deposit is True
    assert res.amount_toman == 55937
    assert res.amount_rial == 559370
    assert res.bank_name == "بلوبانک"


def test_parse_vepod_toman():
    sms = """ویپاد (ترابانک پاسارگاد)
واریز به حساب دیجیتال
مبلغ: 50,250 تومان
مانده: 250,000 تومان"""
    res = parse_bank_sms(sms)
    assert res.is_deposit is True
    assert res.amount_toman == 50250
    assert res.amount_rial == 502500
    assert res.bank_name == "ویپاد"


def test_parse_masken_rial():
    sms = """بانک مسکن
واریز: 559,370 ریال
به کارت 6280***4762
ارجاع: 11223344"""
    res = parse_bank_sms(sms)
    assert res.is_deposit is True
    assert res.amount_toman == 55937
    assert res.card_last4 == "4762"
    assert res.bank_name == "بانک مسکن"


def test_reject_withdrawal_and_otp():
    withdrawal = """بانک ملت
برداشت از حساب: 1234
مبلغ: 559,370 ریال
خرید اینترنتی"""
    res = parse_bank_sms(withdrawal)
    assert res.is_deposit is False
    assert res.amount_toman is None

    otp = "رمز یکبار مصرف شما: 456789 جهت ورود به همراه بانک"
    res_otp = parse_bank_sms(otp)
    assert res_otp.is_deposit is False

    outbound_card = "بانک ملی\nانتقال از کارت 603799***1234 به 502229***5678\nمبلغ: 50,000 تومان"
    res_outbound = parse_bank_sms(outbound_card)
    assert res_outbound.is_deposit is False

    failed_sms = "واریز به حساب شما به مبلغ 100,000 ریال ناموفق بود و به مبدأ برگشت داده شد."
    res_failed = parse_bank_sms(failed_sms)
    assert res_failed.is_deposit is False


def test_parse_saderat_with_plus():
    sms = """بانک صادرات ایران
انتقال به کارت 6037***9900
مبلغ: 50,200+ ریال
مانده: 1,000,000 ریال"""
    res = parse_bank_sms(sms)
    assert res.is_deposit is True
    assert res.amount_toman == 5020
    assert res.card_last4 == "9900"
    assert res.bank_name == "بانک صادرات"


def test_parse_tejarat_deposit():
    sms = """بانک تجارت
واریز 120,500 ریال
به حساب شما
مانده 5,000,000 ریال"""
    res = parse_bank_sms(sms)
    assert res.is_deposit is True
    assert res.amount_toman == 12050
    assert res.bank_name == "بانک تجارت"


def test_parse_resalat_deposit():
    sms = """بانک قرض الحسنه رسالت
واریز به سپرده: 10.203040.1
مبلغ: 75,000 تومان
مانده: 200,000 تومان"""
    res = parse_bank_sms(sms)
    assert res.is_deposit is True
    assert res.amount_toman == 75000
    assert res.bank_name == "بانک رسالت"


def test_parse_blubank_neshast_sms():
    sms = """واریز پول
محمدجواد عزیز، 11,421,100ریال به حساب شما نشست.
موجودی: 781,437,047 ریال
۱۳:۳۰
۱۴۰۵.۰۸.۰۸"""
    res = parse_bank_sms(sms)
    assert res.is_deposit is True
    assert res.amount_rial == 11421100
    assert res.amount_toman == 1142110
    assert res.bank_name == "بلوبانک"


def test_parse_refah_plus_deposit_sms():
    sms = """بانک رفاه
حساب216357100
کارت700,000+
مانده33,066,894
08/07-21:04"""
    res = parse_bank_sms(sms)
    assert res.is_deposit is True
    assert res.amount_rial == 700000
    assert res.amount_toman == 70000
    assert res.bank_name == "بانک رفاه"
    assert res.card_last4 == "7100"


def test_reject_refah_minus_withdrawal_sms():
    sms = """بانک رفاه
حساب216357100
خرید1,290,000-
مانده31,776,894
08/08-07:27"""
    res = parse_bank_sms(sms)
    assert res.is_deposit is False

