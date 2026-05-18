from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from flux.sim.live_extract import rows_to_history_points
from flux.trace.models import TraceCacheCursor, TraceCachePoint, TraceProfile, TraceSignal
from trace.data_plane import dense_y_values_by_signal


@dataclass(frozen=True)
class TraceCacheSyncResult:
    profile_count: int
    signal_count: int
    point_count: int


def trace_cache_payload(profile: TraceProfile, *, window_minutes: int | None = None, step_minutes: int = 1) -> dict:
    signals = list(profile.signals.select_related("tag").filter(default_visible=True).order_by("sort_order", "id"))
    if not signals:
        return empty_payload(profile, window_minutes=window_minutes)
    window_minutes = window_minutes or profile.cache_window_minutes
    step_minutes = max(1, step_minutes)
    latest = latest_cache_timestamp(signals)
    end = latest or timezone.now().replace(second=0, microsecond=0)
    end = end.replace(second=0, microsecond=0) + timezone.timedelta(minutes=1)
    start = end - timezone.timedelta(minutes=window_minutes)
    start_epoch = int(start.timestamp())
    end_epoch = int(end.timestamp())
    x_values = list(range(start_epoch, end_epoch, step_minutes * 60))
    y_values_by_signal = dense_y_values_by_signal(signals=signals, start=start, end=end, start_epoch=start_epoch, point_count=len(x_values), step_minutes=step_minutes)
    return {
        "x": x_values,
        "series": [series_payload(signal, y_values_by_signal[signal.id]) for signal in signals],
        "axisGroups": axis_groups(signals),
        "latestReadAt": (end - timezone.timedelta(minutes=1)).isoformat(),
        "windowDays": window_minutes / 1440,
        "windowMinutes": window_minutes,
        "stepMinutes": step_minutes,
        "windowLabel": window_label(window_minutes),
        "source": "trace-cache",
        "profileKey": profile.key,
        "profileLabel": profile.label,
    }


def sync_trace_cache(fx: Any, *, profile_key: str | None = None, now=None, force: bool = False) -> TraceCacheSyncResult:
    now = now or timezone.now()
    profiles = TraceProfile.objects.filter(enabled=True, cache_enabled=True).prefetch_related("signals__tag")
    if profile_key:
        profiles = profiles.filter(key=profile_key)
    profile_count = 0
    signal_count = 0
    point_count = 0
    for profile in profiles:
        signals = due_signals(profile, now=now, force=force)
        if not signals:
            continue
        profile_count += 1
        signal_count += len(signals)
        point_count += sync_profile_signals(fx, profile=profile, signals=signals, now=now)
        prune_profile_cache(profile, now=now)
    return TraceCacheSyncResult(profile_count=profile_count, signal_count=signal_count, point_count=point_count)


def due_signals(profile: TraceProfile, *, now, force: bool = False) -> list[TraceSignal]:
    signals = list(profile.signals.select_related("tag", "cache_cursor").filter(cache_enabled=True).order_by("sort_order", "id"))
    if force:
        return signals
    due = []
    for signal in signals:
        cursor = getattr(signal, "cache_cursor", None)
        if cursor is None or cursor.last_sync_at is None:
            due.append(signal)
            continue
        age = (now - cursor.last_sync_at).total_seconds()
        if age >= profile.sync_interval_seconds:
            due.append(signal)
    return due


def sync_profile_signals(fx: Any, *, profile: TraceProfile, signals: list[TraceSignal], now) -> int:
    start = min(query_start(signal, profile=profile, now=now) for signal in signals)
    end = now.replace(second=0, microsecond=0) + timezone.timedelta(minutes=1)
    rows = fx.historian.query_raw_points(
        [signal.historian_path for signal in signals],
        int(start.timestamp() * 1000),
        int(end.timestamp() * 1000),
        return_size=profile.max_query_points,
    )
    points = rows_to_history_points(rows, tag_names=[str(signal.id) for signal in signals])
    signal_by_key = {str(signal.id): signal for signal in signals}
    cache_points_by_key = {}
    latest_by_signal: dict[int, Any] = {}
    for point in points:
        signal = signal_by_key.get(point.tag_name)
        if signal is None or not is_number(point.value):
            continue
        timestamp = timezone.datetime.fromtimestamp(point.timestamp_ms / 1000, tz=timezone.get_current_timezone())
        cache_points_by_key[(signal.id, timestamp)] = TraceCachePoint(
            signal=signal,
            timestamp=timestamp,
            value_float=float(point.value),
            quality_code="Good" if str(point.quality) == "192" else str(point.quality),
        )
        if signal.id not in latest_by_signal or timestamp > latest_by_signal[signal.id]:
            latest_by_signal[signal.id] = timestamp
    with transaction.atomic():
        cache_points = list(cache_points_by_key.values())
        if cache_points:
            TraceCachePoint.objects.bulk_create(
                cache_points,
                batch_size=5000,
                update_conflicts=True,
                update_fields=["value_float", "quality_code", "updated_at"],
                unique_fields=["signal", "timestamp"],
            )
        for signal in signals:
            TraceCacheCursor.objects.update_or_create(
                signal=signal,
                defaults={
                    "last_timestamp": latest_by_signal.get(signal.id, getattr(getattr(signal, "cache_cursor", None), "last_timestamp", None)),
                    "last_sync_at": now,
                    "last_error": "",
                },
            )
    return len(cache_points)


def latest_cache_timestamp(signals: list[TraceSignal]):
    return TraceCachePoint.objects.filter(signal__in=signals).order_by("-timestamp").values_list("timestamp", flat=True).first()


def series_payload(signal: TraceSignal, y_values: list[float | None]) -> dict:
    return {
        "rawCount": len(y_values),
        "tagId": signal.tag_id,
        "signalId": signal.id,
        "name": signal.display_label,
        "fullPath": signal.tag.full_path,
        "unit": signal.display_unit,
        "axisKey": signal.axis_key,
        "x": [],
        "y": y_values,
    }


def axis_groups(signals: list[TraceSignal]) -> list[dict]:
    groups = {}
    for index, signal in enumerate(signals, start=1):
        groups.setdefault(
            signal.axis_key,
            {
                "key": signal.axis_key,
                "label": signal.axis_label or signal.axis_key.replace("-", " ").title(),
                "unit": signal.axis_unit or signal.display_unit,
                "range": axis_range(signal),
                "side": 1 if index == 1 else 3,
            },
        )
    return list(groups.values())


def axis_range(signal: TraceSignal) -> list[float] | None:
    if signal.range_min is None or signal.range_max is None:
        return None
    return [signal.range_min, signal.range_max]


def empty_payload(profile: TraceProfile, *, window_minutes: int | None) -> dict:
    return {
        "x": [],
        "series": [],
        "axisGroups": [],
        "latestReadAt": None,
        "windowDays": (window_minutes or profile.cache_window_minutes) / 1440,
        "windowLabel": window_label(window_minutes or profile.cache_window_minutes),
        "source": "trace-cache",
        "profileKey": profile.key,
        "profileLabel": profile.label,
    }


def query_start(signal: TraceSignal, *, profile: TraceProfile, now):
    cursor = getattr(signal, "cache_cursor", None)
    if cursor is not None and cursor.last_timestamp is not None:
        return cursor.last_timestamp + timezone.timedelta(milliseconds=1)
    return now - timezone.timedelta(minutes=profile.cache_window_minutes)


def prune_profile_cache(profile: TraceProfile, *, now) -> int:
    cutoff = now - timezone.timedelta(minutes=profile.cache_window_minutes)
    deleted, _details = TraceCachePoint.objects.filter(signal__profile=profile, timestamp__lt=cutoff).delete()
    return deleted


def is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def window_label(window_minutes: int) -> str:
    if window_minutes % 1440 == 0:
        days = window_minutes // 1440
        return "%s day%s" % (days, "" if days == 1 else "s")
    return "%s min" % window_minutes
