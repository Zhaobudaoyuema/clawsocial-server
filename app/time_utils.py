from datetime import datetime
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def now_beijing() -> datetime:
    """Return timezone-aware Asia/Shanghai datetime."""
    return datetime.now(BEIJING_TZ)


def coerce_beijing(dt: datetime | None) -> datetime | None:
    """Normalize DB naive datetimes to Asia/Shanghai aware for arithmetic."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BEIJING_TZ)
    return dt.astimezone(BEIJING_TZ)
