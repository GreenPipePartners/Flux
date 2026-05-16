from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN
from math import ceil
from typing import Any

from django.conf import settings
from django.utils import timezone

from flux.base.runtime import RuntimeTag
from flux.base.runtime_extremes import rolling_midnight_extremes


@dataclass(frozen=True)
class HistoricalExtreme:
    label: str
    min_value: str
    max_value: str
    marker_percent: int


@dataclass(frozen=True)
class LivePoint:
    label: str
    value: Any
    display_value: str
    units: str
    quality: str
    read_at: Any
    stale: bool
    full_path: str
    next_read_seconds: int | None
    countdown_percent: int
    history: list[HistoricalExtreme]


@dataclass(frozen=True)
class LiveCard:
    title: str
    equipment_type: str
    points: list[LivePoint]


def pad_overview_cards(*, tag_prefix: str = "FluxLiveDemo", now=None) -> list[LiveCard]:
    now = now or timezone.now()
    stale_after_seconds = settings.STALE_AFTER_SECONDS
    tags = (
        RuntimeTag.objects.select_related("latest_value", "schedule")
        .filter(enabled=True, path__startswith=tag_prefix)
        .order_by("asset_name", "display_name")
    )
    tags = list(tags)
    history_by_tag = rolling_midnight_extremes(tags, now=now)
    grouped: dict[str, list[LivePoint]] = {}
    for tag in tags:
        value = getattr(tag, "latest_value", None)
        grouped.setdefault(tag.asset_name or "Unassigned", []).append(
            LivePoint(
                label=tag.display_name,
                value=value.value if value else None,
                display_value=format_live_value(value.value if value else None),
                units=tag.engineering_units,
                quality=value.quality_code if value else "Missing",
                read_at=value.read_at if value else None,
                stale=value.is_stale(now, stale_after_seconds) if value else True,
                full_path=tag.full_path,
                next_read_seconds=next_read_seconds(tag, value, now),
                countdown_percent=countdown_percent(tag, value, now),
                history=historical_extremes(history_by_tag.get(tag.id, {}), current_value=value.value if value else None),
            )
        )
    return [
        LiveCard(title=asset_name, equipment_type=equipment_type(asset_name), points=points)
        for asset_name, points in grouped.items()
    ]


def equipment_type(asset_name: str) -> str:
    if ":" not in asset_name:
        return "Equipment"
    return asset_name.split(":", 1)[0].strip()


def next_read_seconds(tag: RuntimeTag, value: Any, now) -> int | None:
    if value is None or value.read_at is None:
        return None
    next_read_at = value.read_at + timedelta(seconds=tag.schedule.interval_seconds)
    return max(0, ceil((next_read_at - now).total_seconds()))


def countdown_percent(tag: RuntimeTag, value: Any, now) -> int:
    seconds = next_read_seconds(tag, value, now)
    if seconds is None:
        return 0
    interval = max(tag.schedule.interval_seconds, 1)
    return max(0, min(100, round((seconds / interval) * 100)))


def format_live_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        truncated = Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_DOWN)
        return f"{truncated:.3f}"
    return str(value)


def historical_extremes(values_by_days: dict[int, Any], *, current_value: Any) -> list[HistoricalExtreme]:
    return [
        HistoricalExtreme(
            label=label,
            min_value=format_live_value(extreme.min_value),
            max_value=format_live_value(extreme.max_value),
            marker_percent=range_marker_percent(current_value, extreme.min_value, extreme.max_value),
        )
        for days, label in ((1, "24h"), (7, "7d"), (30, "30d"))
        if (extreme := values_by_days.get(days)) is not None
    ]


def range_marker_percent(value: Any, min_value: float, max_value: float) -> int:
    numeric = value if isinstance(value, int | float) and not isinstance(value, bool) else None
    if numeric is None or min_value == max_value:
        return 50
    percent = ((float(numeric) - min_value) / (max_value - min_value)) * 100
    return max(0, min(100, round(percent)))
