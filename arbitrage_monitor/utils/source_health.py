from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from utils.db_manager import DBManager


db_manager = DBManager()


def record_source_health(
    source_name: str,
    *,
    success: bool,
    duration_ms: float,
    active_source: str = "primary",
    is_fallback: bool = False,
    error_summary: str = "",
) -> None:
    db_manager.save_source_health_status(
        source_name,
        success=success,
        duration_ms=duration_ms,
        active_source=active_source,
        is_fallback=is_fallback,
        error_summary=error_summary,
    )


@contextmanager
def source_health_context(
    source_name: str,
    *,
    active_source: str = "primary",
    is_fallback: bool = False,
) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        record_source_health(
            source_name,
            success=False,
            duration_ms=(time.perf_counter() - started) * 1000,
            active_source=active_source,
            is_fallback=is_fallback,
            error_summary=str(exc),
        )
        raise
    else:
        record_source_health(
            source_name,
            success=True,
            duration_ms=(time.perf_counter() - started) * 1000,
            active_source=active_source,
            is_fallback=is_fallback,
        )
