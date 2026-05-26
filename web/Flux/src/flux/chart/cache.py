from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from flux.plane.models import Sample
from flux.plane.services import ensure_series_for_full_path
from flux.sim.live_extract import rows_to_history_points
from flux.trace.models import TraceCacheCursor, TraceProfile, TraceSignal
from flux.chart.data_plane import plane_sample_epoch_rows

@dataclass(frozen=True)
class PlaneSampleSyncResult:
    profile_count: int
    signal_count: int
    point_count: int


def plane_sample_payload(profile: TraceProfile, *, window_minutes: int | None = None, step_minutes: int = 1) -> dict:
    signals = list(profile.signals.select_related("tag", "series", "series__base_tag").filter(default_visible=True).order_by("sort_order", "id"))
    signals = ensure_signals_have_series(signals)
    if not signals:
        return empty_payload(profile, window_minutes=window_minutes)
    window_minutes = window_minutes or profile.cache_window_minutes
    step_minutes = max(1, step_minutes)
    latest = latest_plane_sample_timestamp(signals)
    end = latest or timezone.now().replace(second=0, microsecond=0)
    end = end.replace(second=0, microsecond=0) + timezone.timedelta(minutes=1)
    start = end - timezone.timedelta(minutes=window_minutes)
    x_values, y_values_by_signal, raw_counts = sampled_plane_sample_values(
        signals=signals,
        start=start,
        end=end,
        start_epoch=int(start.timestamp()),
        step_minutes=step_minutes,
    )
    return {
        "x": x_values,
        "series": [series_payload(signal, y_values_by_signal[signal.id], raw_counts[signal.id]) for signal in signals],
        "axisGroups": axis_groups(signals),
        "latestReadAt": (end - timezone.timedelta(minutes=1)).isoformat(),
        "windowDays": window_minutes / 1440,
        "windowMinutes": window_minutes,
        "stepMinutes": step_minutes,
        "windowLabel": window_label(window_minutes),
        "source": "plane-samples",
        "profileKey": profile.key,
        "profileLabel": profile.label,
    }


def sync_plane_samples(fx: Any, *, profile_key: str | None = None, now=None, force: bool = False) -> PlaneSampleSyncResult:
    now = now or timezone.now()
    profiles = TraceProfile.objects.filter(enabled=True, cache_enabled=True).prefetch_related("signals__tag", "signals__series__base_tag")
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
        prune_profile_samples(profile, now=now)
    return PlaneSampleSyncResult(profile_count=profile_count, signal_count=signal_count, point_count=point_count)


def due_signals(profile: TraceProfile, *, now, force: bool = False) -> list[TraceSignal]:
    signals = list(profile.signals.select_related("tag", "series", "series__base_tag", "cache_cursor").filter(cache_enabled=True).order_by("sort_order", "id"))
    signals = ensure_signals_have_series(signals)
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
    signals = ensure_signals_have_series(signals)
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
    sample_rows_by_key = {}
    latest_by_signal: dict[int, Any] = {}
    for point in points:
        signal = signal_by_key.get(point.tag_name)
        if signal is None or not is_number(point.value):
            continue
        timestamp = timezone.datetime.fromtimestamp(point.timestamp_ms / 1000, tz=timezone.get_current_timezone())
        if signal.series_id is None:
            continue
        sample_rows_by_key[(signal.series_id, timestamp)] = Sample(
            series_id=signal.series_id,
            timestamp=timestamp,
            value_float=float(point.value),
            quality_code="Good" if str(point.quality) == "192" else str(point.quality),
        )
        if signal.id not in latest_by_signal or timestamp > latest_by_signal[signal.id]:
            latest_by_signal[signal.id] = timestamp
    with transaction.atomic():
        sample_rows = list(sample_rows_by_key.values())
        if sample_rows:
            Sample.objects.bulk_create(
                sample_rows,
                batch_size=5000,
                update_conflicts=True,
                update_fields=["value_float", "quality_code", "updated_at"],
                unique_fields=["series", "timestamp"],
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
    return len(sample_rows)


def latest_plane_sample_timestamp(signals: list[TraceSignal]):
    series_ids = [signal.series_id for signal in signals if signal.series_id]
    if not series_ids:
        return None
    return Sample.objects.filter(series_id__in=series_ids).order_by("-timestamp").values_list("timestamp", flat=True).first()


def sampled_plane_sample_values(
    *,
    signals: list[TraceSignal],
    start,
    end,
    start_epoch: int,
    step_minutes: int = 1,
) -> tuple[list[int], dict[int, list[float | None]], dict[int, int]]:
    y_values_by_signal: dict[int, list[float | None]] = {signal.id: [] for signal in signals}
    raw_counts: dict[int, int] = {signal.id: 0 for signal in signals}
    if not signals:
        return [], y_values_by_signal, raw_counts

    step_seconds = max(1, step_minutes) * 60
    selected_points: dict[tuple[int, int], tuple[int, float]] = {}
    for signal_id, epoch_seconds, value in plane_sample_epoch_rows(signals=signals, start=start, end=end):
        if step_minutes > 1:
            offset_seconds = epoch_seconds - start_epoch
            if offset_seconds < 0:
                continue
            bucket = offset_seconds // step_seconds
        else:
            bucket = epoch_seconds
        selected_points[(signal_id, bucket)] = (epoch_seconds, value)

    x_values = sorted({epoch_seconds for epoch_seconds, _value in selected_points.values()})
    x_index = {epoch_seconds: index for index, epoch_seconds in enumerate(x_values)}
    y_values_by_signal = {signal.id: [None] * len(x_values) for signal in signals}
    for (signal_id, _bucket), (epoch_seconds, value) in selected_points.items():
        y_values_by_signal[signal_id][x_index[epoch_seconds]] = value
        raw_counts[signal_id] += 1
    return x_values, y_values_by_signal, raw_counts


def series_payload(signal: TraceSignal, y_values: list[float | None], raw_count: int) -> dict:
    return {
        "rawCount": raw_count,
        "tagId": signal.tag_id,
        "seriesId": signal.series_id,
        "storageKey": signal.series_storage_key,
        "signalId": signal.id,
        "name": signal.display_label,
        "fullPath": signal.chart_full_path,
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
        "source": "plane-samples",
        "profileKey": profile.key,
        "profileLabel": profile.label,
    }


def query_start(signal: TraceSignal, *, profile: TraceProfile, now):
    cursor = getattr(signal, "cache_cursor", None)
    if cursor is not None and cursor.last_timestamp is not None:
        return cursor.last_timestamp + timezone.timedelta(milliseconds=1)
    return now - timezone.timedelta(minutes=profile.cache_window_minutes)


def prune_profile_samples(profile: TraceProfile, *, now) -> int:
    return 0


def ensure_signals_have_series(signals: list[TraceSignal]) -> list[TraceSignal]:
    updates = []
    for signal in signals:
        if signal.series_id is not None:
            continue
        series = ensure_series_for_full_path(signal.tag.full_path)
        signal.series = series
        updates.append(signal)
    if updates:
        TraceSignal.objects.bulk_update(updates, ["series"], batch_size=5000)
    return signals


def is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def window_label(window_minutes: int) -> str:
    if window_minutes % 1440 == 0:
        days = window_minutes // 1440
        return "%s day%s" % (days, "" if days == 1 else "s")
    return "%s min" % window_minutes
