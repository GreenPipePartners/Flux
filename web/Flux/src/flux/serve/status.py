from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils import timezone


@dataclass(frozen=True)
class RuntimeReadStatus:
    online: bool
    stale: bool
    bad_quality: bool
    reason: str
    age_seconds: int | None = None

    @property
    def state(self) -> str:
        if self.online:
            return "online"
        if self.bad_quality:
            return "bad_quality"
        if self.stale:
            return "stale"
        return "unknown"


def runtime_read_status(value: Any, *, now, stale_after_seconds: int) -> RuntimeReadStatus:
    if value is None:
        return RuntimeReadStatus(False, True, False, "No read recorded")
    if value.quality_code.lower() != "good":
        return RuntimeReadStatus(
            online=False,
            stale=True,
            bad_quality=True,
            reason="Bad quality: %s" % value.quality_code,
            age_seconds=read_age_seconds(value, now),
        )
    if value.is_stale(now, stale_after_seconds):
        return RuntimeReadStatus(
            online=False,
            stale=True,
            bad_quality=False,
            reason="Last read older than %ss" % stale_after_seconds,
            age_seconds=read_age_seconds(value, now),
        )
    return RuntimeReadStatus(True, False, False, "Good", read_age_seconds(value, now))


def read_age_seconds(value: Any, now) -> int | None:
    if value is None or value.read_at is None:
        return None
    return int((now - value.read_at).total_seconds())


def heartbeat_age_seconds(heartbeat: Any, now) -> int | None:
    if heartbeat is None or heartbeat.last_seen_at is None:
        return None
    return int((now - heartbeat.last_seen_at).total_seconds())


def serve_heartbeat_status(heartbeats, *, now=None, stale_after_seconds: int = 120) -> dict[str, Any]:
    now = now or timezone.now()
    items = []
    running_count = 0
    stale_count = 0
    error_count = 0
    for heartbeat in heartbeats:
        age_seconds = heartbeat_age_seconds(heartbeat, now)
        is_stale = age_seconds is None or age_seconds > stale_after_seconds
        is_running = heartbeat.status == "running" and not is_stale
        is_error = heartbeat.status == "error"
        running_count += 1 if is_running else 0
        stale_count += 1 if is_stale else 0
        error_count += 1 if is_error else 0
        items.append(
            {
                "heartbeat": heartbeat,
                "age_seconds": age_seconds,
                "running": is_running,
                "stale": is_stale,
                "error": is_error,
                "state": "error" if is_error else "stale" if is_stale else heartbeat.status,
            }
        )
    total_count = len(items)
    state = "ok" if total_count and running_count == total_count else "error" if error_count or not total_count else "warning"
    return {
        "state": state,
        "total_count": total_count,
        "running_count": running_count,
        "stale_count": stale_count,
        "error_count": error_count,
        "items": items,
    }
