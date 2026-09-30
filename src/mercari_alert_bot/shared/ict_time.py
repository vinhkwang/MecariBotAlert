from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

ICT_TIMEZONE: Final = ZoneInfo("Asia/Ho_Chi_Minh")
_ICT_TIMESTAMP_FORMAT: Final = "%Y-%m-%d %H:%M ICT"


def format_ict_timestamp(moment: datetime) -> str:
    if moment.utcoffset() is None:
        raise ValueError("moment must be timezone-aware")
    return moment.astimezone(ICT_TIMEZONE).strftime(_ICT_TIMESTAMP_FORMAT)
