from decimal import Decimal


def format_decimal(value: Decimal) -> str:
    """Format a Decimal without insignificant fractional trailing zeroes."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
