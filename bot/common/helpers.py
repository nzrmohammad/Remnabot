"""Common text parsing and sanitization utilities."""

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def parse_int(text: str) -> int | None:
    """Parse integer from Persian/Arabic/English text, stripping commas and whitespace."""
    if not text:
        return None
    cleaned = text.translate(_DIGIT_MAP).replace(",", "").replace("،", "").strip()
    if not cleaned.isdigit() and not (cleaned.startswith("-") and cleaned[1:].isdigit()):
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None
