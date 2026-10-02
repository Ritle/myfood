from decimal import Decimal

from app.utils.formatting import format_decimal


def test_format_decimal_keeps_integer_trailing_zeroes() -> None:
    assert format_decimal(Decimal(190)) == "190"
    assert format_decimal(Decimal("2100.00")) == "2100"
    assert format_decimal(Decimal("187.50")) == "187.5"
    assert format_decimal(Decimal("0.00")) == "0"
