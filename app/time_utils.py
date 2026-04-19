from datetime import datetime
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def now_beijing() -> datetime:
    """Return timezone-aware Asia/Shanghai datetime."""
    return datetime.now(BEIJING_TZ)
