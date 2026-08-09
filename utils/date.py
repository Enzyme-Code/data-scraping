from datetime import date, datetime
from typing import Optional, Union

_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y%m%d%H%M%S",
)

_DATE_ONLY_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y%m%d",
)


def to_iso_date(value: Union[str, date, datetime, None]) -> Optional[str]:
    """
    Normalize a date/datetime value of any common shape into an ISO-style
    string. The date portion is always normalized to YYYY-MM-DD; any
    existing time-of-day is preserved (as "YYYY-MM-DD HH:MM:SS") rather
    than discarded. Returns None if value is empty or unparseable.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("T", " ").split("+")[0].split(".")[0].strip()

    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    for fmt in _DATE_ONLY_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).date().isoformat()
        except ValueError:
            continue

    return None
