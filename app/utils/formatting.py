from decimal import Decimal


def format_decimal(value: Decimal) -> str:
    """Format a Decimal without insignificant trailing zeroes."""
    return format(value, "f").rstrip("0").rstrip(".") or "0"
