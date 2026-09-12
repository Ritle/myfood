from decimal import Decimal, InvalidOperation


def parse_decimal(raw: str | None) -> Decimal | None:
    """Parse a finite decimal number allowing comma as decimal separator."""
    try:
        value = Decimal((raw or "").strip().replace(",", "."))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def parse_integer(raw: str | None) -> int | None:
    """Parse an integer value from user input."""
    try:
        return int((raw or "").strip())
    except ValueError:
        return None
