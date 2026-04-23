from __future__ import annotations

from datetime import datetime, time
from typing import Optional


def parse_optional_time(value: str) -> Optional[time]:
    value = (value or "").strip()
    if not value:
        return None
    return time.fromisoformat(value)


def is_day_session_active(start_value: str, end_value: str, now: datetime) -> bool:
    start = parse_optional_time(start_value)
    end = parse_optional_time(end_value)
    if not start or not end:
        return False
    return now.weekday() < 5 and start <= now.time() <= end


def is_night_session_active(start_value: str, end_value: str, now: datetime) -> bool:
    start = parse_optional_time(start_value)
    end = parse_optional_time(end_value)
    if not start or not end:
        return False

    current_time = now.time()
    if start <= end:
        return now.weekday() < 5 and start <= current_time <= end

    if current_time >= start:
        return now.weekday() < 5
    if current_time <= end:
        return now.weekday() > 0
    return False
