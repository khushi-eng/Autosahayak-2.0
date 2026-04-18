import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


APP_TIMEZONE_NAME = os.getenv("APP_TIMEZONE", "Asia/Kolkata")
try:
    APP_TIMEZONE = ZoneInfo(APP_TIMEZONE_NAME)
except ZoneInfoNotFoundError:
    # Windows Python may require the tzdata package; fall back to UTC so the
    # application can still start cleanly even if timezone data is missing.
    APP_TIMEZONE = timezone.utc


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_datetime_local_input(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=APP_TIMEZONE)
    return parsed.astimezone(timezone.utc)


def to_app_timezone(value: datetime | None) -> datetime | None:
    utc_value = ensure_utc(value)
    if utc_value is None:
        return None
    return utc_value.astimezone(APP_TIMEZONE)


def format_app_datetime(value: datetime | None, fmt: str = "%d %b %Y %I:%M %p") -> str:
    local_value = to_app_timezone(value)
    if local_value is None:
        return ""
    return local_value.strftime(fmt)
