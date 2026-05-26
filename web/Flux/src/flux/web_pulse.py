from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.utils import timezone


DISPLAY_PULSE_SECONDS = 5


def display_pulse_context(
    *,
    source_label: str,
    last_backend_at: Any = None,
    state: str = "ok",
    detail: str = "",
    refresh_seconds: int = DISPLAY_PULSE_SECONDS,
    stale_after_seconds: int | None = None,
) -> dict[str, Any]:
    stale_after = stale_after_seconds if stale_after_seconds is not None else settings.STALE_AFTER_SECONDS
    age_seconds = backend_age_seconds(last_backend_at)
    pulse_state = display_pulse_state(state, age_seconds=age_seconds, stale_after_seconds=stale_after)
    return {
        "enabled": True,
        "refresh_seconds": refresh_seconds,
        "source_label": source_label,
        "last_backend_at": last_backend_at,
        "last_backend_age_seconds": age_seconds,
        "stale_after_seconds": stale_after,
        "state": pulse_state,
        "state_label": display_pulse_state_label(pulse_state),
        "detail": detail,
    }


def latest_timestamp(values: Iterable[Any]) -> Any | None:
    latest = None
    for value in values:
        if value is not None and (latest is None or value > latest):
            latest = value
    return latest


def backend_age_seconds(last_backend_at: Any) -> int | None:
    if last_backend_at is None:
        return None
    return max(0, int((timezone.now() - last_backend_at).total_seconds()))


def display_pulse_state(state: str, *, age_seconds: int | None, stale_after_seconds: int) -> str:
    normalized = (state or "unknown").lower().replace(" ", "-")
    if age_seconds is None and normalized in {"ok", "ready", "trial"}:
        return "unknown"
    if age_seconds is not None and age_seconds > stale_after_seconds and normalized in {"ok", "ready", "trial"}:
        return "stale"
    return normalized


def display_pulse_state_label(state: str) -> str:
    return {
        "ok": "Fresh",
        "ready": "Fresh",
        "trial": "Fresh",
        "warning": "Attention",
        "stale": "Stale",
        "error": "Offline",
        "offline": "Offline",
        "unlicensed": "Offline",
        "unknown": "Waiting",
    }.get(state, state.replace("-", " ").title())
