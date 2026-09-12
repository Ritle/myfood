from datetime import time

from app.services.notification_settings import parse_clock, parse_time_range, parse_timezone


def test_parses_clock_and_time_ranges() -> None:
    assert parse_clock("9:30") == time(9, 30)
    assert parse_clock("23:59") == time(23, 59)
    assert parse_clock("24:00") is None
    assert parse_clock("9:5") is None
    assert parse_time_range("09:00-21:00") == (time(9), time(21))
    assert parse_time_range("22:00–08:00") == (time(22), time(8))
    assert parse_time_range("08:00-08:00") is None
    assert parse_timezone("Europe/Moscow") == "Europe/Moscow"
    assert parse_timezone("Mars/Olympus") is None
