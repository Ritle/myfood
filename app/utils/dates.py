import re
from datetime import date

_ISO_DATE = re.compile(r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})")
_DAY_FIRST_DATE = re.compile(
    r"(?P<day>\d{1,2})(?P<separator>[./-])(?P<month>\d{1,2})"
    r"(?P=separator)(?P<year>\d{4})"
)


def parse_birth_date(raw: str | None) -> date | None:
    """Parse ISO or Russian day-first birth dates with dot, slash, or dash."""
    value = (raw or "").strip()
    match = _ISO_DATE.fullmatch(value) or _DAY_FIRST_DATE.fullmatch(value)
    if match is None:
        return None

    try:
        return date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError:
        return None
