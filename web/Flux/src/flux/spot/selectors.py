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
from flux.plane.models import Series, WindowStat
from flux.serve.status import runtime_read_status

from .models import LiveScope


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
    next_read_centiseconds: int | None = None
    next_read_label: str = ""
    refresh_interval_centiseconds: int = 0

    @property
    def quality_good(self) -> bool:
        return self.quality.lower() == "good"

    @property
    def error(self) -> bool:
        return not self.quality_good or self.stale


@dataclass(frozen=True)
class LiveCard:
    title: str
    group: str
    kind: str
    points: list[LivePoint]
    copy_table_markdown: str = ""
    copy_llm_markdown: str = ""

    @property
    def equipment_type(self) -> str:
        return self.group or self.kind


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
                stale=live_value_is_stale(value, now, stale_after_seconds),
                full_path=tag.full_path,
                next_read_seconds=next_read_seconds(tag, value, now),
                next_read_centiseconds=next_read_centiseconds(tag, value, now),
                next_read_label=next_read_label(tag, value, now),
                refresh_interval_centiseconds=refresh_interval_centiseconds(tag),
                countdown_percent=countdown_percent(tag, value, now),
                history=historical_extremes(history_by_tag.get(tag.id, {}), current_value=value.value if value else None),
            )
        )
    return [
        LiveCard(title=asset_name, group="", kind=kind_from_asset_name(asset_name), points=points)
        for asset_name, points in grouped.items()
    ]


def kind_from_asset_name(asset_name: str) -> str:
    if ":" not in asset_name:
        return "Equipment"
    return asset_name.split(":", 1)[0].strip()


def scope_cards(scope_slug: str, *, now=None) -> list[LiveCard]:
    now = now or timezone.now()
    stale_after_seconds = settings.STALE_AFTER_SECONDS
    scope = (
        LiveScope.objects.prefetch_related("cards__points__series")
        .filter(slug=scope_slug, enabled=True)
        .first()
    )
    if scope is None:
        return []

    point_defs = [
        point_def
        for card_def in scope.cards.all()
        if card_def.enabled
        for point_def in card_def.points.all()
        if point_def.enabled
    ]
    series_ids = [point_def.series_id for point_def in point_defs if point_def.series_id]
    series_by_id = {
        series.id: series
        for series in Series.objects.select_related("base_tag", "latest")
        .prefetch_related("window_stats")
        .filter(id__in=series_ids)
    }
    missing_plane_points = [
        point_def
        for point_def in point_defs
        if point_def.series_id is None or getattr(series_by_id.get(point_def.series_id), "latest", None) is None
    ]
    tag_keys = [parse_full_tag_path(point_def.full_path) for point_def in missing_plane_points]
    runtime_tags = RuntimeTag.objects.select_related("latest_value", "schedule").filter(
        enabled=True,
        provider__in={provider for provider, _path in tag_keys},
        path__in={path for _provider, path in tag_keys},
    )
    tags_by_full_path = {tag.full_path: tag for tag in runtime_tags}
    history_by_tag = rolling_midnight_extremes(list(tags_by_full_path.values()), now=now)

    cards = []
    for card_def in scope.cards.all():
        if not card_def.enabled:
            continue
        points = []
        for point_def in card_def.points.all():
            if not point_def.enabled:
                continue
            series = series_by_id.get(point_def.series_id) if point_def.series_id else None
            if series is not None and getattr(series, "latest", None) is not None:
                points.append(live_point_from_plane(point_def, series, now=now, stale_after_seconds=stale_after_seconds))
            else:
                tag = tags_by_full_path.get(point_def.full_path)
                points.append(
                    live_point_from_definition(
                        point_def,
                        tag,
                        history_by_tag=history_by_tag,
                        now=now,
                        stale_after_seconds=stale_after_seconds,
                    )
                )
        cards.append(LiveCard(title=card_def.title, group=card_def.group, kind=card_def.kind, points=points))
    return cards


def live_point_from_plane(point_def, series: Series, *, now, stale_after_seconds) -> LivePoint:
    latest = getattr(series, "latest", None)
    return LivePoint(
        label=point_def.label,
        value=latest.value if latest else None,
        display_value=format_live_value(latest.value if latest else None),
        units="",
        quality=latest.quality_code if latest else "Missing",
        read_at=latest.read_at if latest else None,
        stale=plane_value_is_stale(latest, now, stale_after_seconds),
        full_path=series.storage_key,
        next_read_seconds=plane_next_read_seconds(series, latest, now),
        next_read_centiseconds=plane_next_read_centiseconds(series, latest, now),
        next_read_label=plane_next_read_label(series, latest, now),
        refresh_interval_centiseconds=plane_refresh_interval_centiseconds(series),
        countdown_percent=plane_countdown_percent(series, latest, now),
        history=plane_historical_extremes(series.window_stats.all(), current_value=latest.value if latest else None),
    )


def live_point_from_definition(point_def, tag, *, history_by_tag, now, stale_after_seconds) -> LivePoint:
    value = getattr(tag, "latest_value", None) if tag is not None else None
    return LivePoint(
        label=point_def.label,
        value=value.value if value else None,
        display_value=format_live_value(value.value if value else None),
        units=tag.engineering_units if tag is not None else "",
        quality=value.quality_code if value else "Missing",
        read_at=value.read_at if value else None,
        stale=live_value_is_stale(value, now, stale_after_seconds),
        full_path=point_def.full_path,
        next_read_seconds=next_read_seconds(tag, value, now) if tag is not None else None,
        next_read_centiseconds=next_read_centiseconds(tag, value, now) if tag is not None else None,
        next_read_label=next_read_label(tag, value, now) if tag is not None else "",
        refresh_interval_centiseconds=refresh_interval_centiseconds(tag) if tag is not None else 0,
        countdown_percent=countdown_percent(tag, value, now) if tag is not None else 0,
        history=historical_extremes(
            history_by_tag.get(tag.id, {}) if tag is not None else {},
            current_value=value.value if value else None,
        ),
    )


def parse_full_tag_path(full_path: str) -> tuple[str, str]:
    if not full_path.startswith("[") or "]" not in full_path:
        raise ValueError("canonical tag references must be full [provider]path values")
    provider, path = full_path[1:].split("]", 1)
    if not provider or not path:
        raise ValueError("canonical tag references must be full [provider]path values")
    return provider, path


def next_read_seconds(tag: RuntimeTag, value: Any, now) -> int | None:
    centiseconds = next_read_centiseconds(tag, value, now)
    if centiseconds is None:
        return None
    return ceil(centiseconds / 100)


def next_read_centiseconds(tag: RuntimeTag, value: Any, now) -> int | None:
    if value is None or value.read_at is None:
        return None
    next_read_at = value.read_at + timedelta(seconds=tag.schedule.interval_seconds)
    return max(0, ceil((next_read_at - now).total_seconds() * 100))


def next_read_label(tag: RuntimeTag, value: Any, now) -> str:
    centiseconds = next_read_centiseconds(tag, value, now)
    if centiseconds is None:
        return ""
    if refresh_interval_centiseconds(tag) <= 100:
        return f"{centiseconds}cs"
    return f"{ceil(centiseconds / 100)}s"


def refresh_interval_centiseconds(tag: RuntimeTag) -> int:
    return max(1, tag.schedule.interval_seconds * 100)


def live_value_is_stale(value: Any, now, stale_after_seconds: int) -> bool:
    return runtime_read_status(value, now=now, stale_after_seconds=stale_after_seconds).stale


def plane_value_is_stale(value: Any, now, stale_after_seconds: int) -> bool:
    if value is None or value.read_at is None:
        return True
    return (now - value.read_at).total_seconds() > stale_after_seconds


def plane_next_read_seconds(series: Series, value: Any, now) -> int | None:
    centiseconds = plane_next_read_centiseconds(series, value, now)
    if centiseconds is None:
        return None
    return ceil(centiseconds / 100)


def plane_next_read_centiseconds(series: Series, value: Any, now) -> int | None:
    if value is None or value.read_at is None:
        return None
    next_read_at = value.read_at + timedelta(milliseconds=series.sample_interval_ms)
    return max(0, ceil((next_read_at - now).total_seconds() * 100))


def plane_next_read_label(series: Series, value: Any, now) -> str:
    centiseconds = plane_next_read_centiseconds(series, value, now)
    if centiseconds is None:
        return ""
    if plane_refresh_interval_centiseconds(series) <= 100:
        return f"{centiseconds}cs"
    return f"{ceil(centiseconds / 100)}s"


def plane_refresh_interval_centiseconds(series: Series) -> int:
    return max(1, ceil(series.sample_interval_ms / 10))


def plane_countdown_percent(series: Series, value: Any, now) -> int:
    centiseconds = plane_next_read_centiseconds(series, value, now)
    if centiseconds is None:
        return 0
    interval = plane_refresh_interval_centiseconds(series)
    return max(0, min(100, round((centiseconds / interval) * 100)))


def countdown_percent(tag: RuntimeTag, value: Any, now) -> int:
    centiseconds = next_read_centiseconds(tag, value, now)
    if centiseconds is None:
        return 0
    interval = refresh_interval_centiseconds(tag)
    return max(0, min(100, round((centiseconds / interval) * 100)))


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


def plane_historical_extremes(stats: list[WindowStat], *, current_value: Any) -> list[HistoricalExtreme]:
    labels = {
        WindowStat.Window.TODAY: "24h",
        WindowStat.Window.ROLLING_7D: "7d",
        WindowStat.Window.ROLLING_30D: "30d",
    }
    order = {
        WindowStat.Window.TODAY: 0,
        WindowStat.Window.ROLLING_7D: 1,
        WindowStat.Window.ROLLING_30D: 2,
    }
    return [
        HistoricalExtreme(
            label=labels[stat.window],
            min_value=format_live_value(stat.min_value),
            max_value=format_live_value(stat.max_value),
            marker_percent=range_marker_percent(current_value, stat.min_value, stat.max_value),
        )
        for stat in sorted(stats, key=lambda item: order.get(item.window, 99))
        if stat.window in labels and stat.min_value is not None and stat.max_value is not None
    ]


def range_marker_percent(value: Any, min_value: float, max_value: float) -> int:
    numeric = value if isinstance(value, int | float) and not isinstance(value, bool) else None
    if numeric is None or min_value == max_value:
        return 50
    percent = ((float(numeric) - min_value) / (max_value - min_value)) * 100
    return max(0, min(100, round(percent)))
