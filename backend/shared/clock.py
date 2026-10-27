"""UTC clock helper (naive UTC datetimes, matching the MVP storage convention)."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
