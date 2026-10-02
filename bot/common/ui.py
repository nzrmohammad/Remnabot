"""Common UI elements, separators and visual constants."""

SEPARATOR: str = "─" * 18


def fmt(amount: int | float) -> str:
    """Format a number with thousands separator commas."""
    return f"{amount:,}"
