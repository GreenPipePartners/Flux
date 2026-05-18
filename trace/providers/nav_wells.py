from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from flux.base.runtime import RuntimeTag, TagSchedule
from flux.nav.registry import NavigationOption, sqlite_options
from flux.sim.live_extract import historical_path, tag_path
from flux.trace.models import TraceCacheCursor, TraceCachePoint, TraceProfile, TraceSignal
from trace.cache import TraceCacheSyncResult, sync_trace_cache


WELL_TRACE_ROOT = "FluxTraceNavWells"
WELL_TRACE_PROFILE_PREFIX = "nav-well"
WELL_TRACE_SCHEDULE = "trace-nav-well-60s"
WELL_TRACE_PROVIDER = "default"
WELL_TRACE_HISTORY_PROVIDER = "Core Historian"
WELL_TRACE_WINDOW_MINUTES = 1440


@dataclass(frozen=True)
class WellTraceTagSpec:
    name: str
    label: str
    unit: str
    data_type: str
    axis_key: str
    axis_label: str
    axis_unit: str
    range_min: float | None
    range_max: float | None
    base: float
    amplitude: float
    phase: float


WELL_TRACE_TAGS = (
    WellTraceTagSpec("PressureA", "Pressure A", "psi", "Float4", "pressure", "Pressure", "psi", 0, 1200, 620, 55, 0.0),
    WellTraceTagSpec("PressureB", "Pressure B", "psi", "Float4", "pressure", "Pressure", "psi", 0, 1200, 390, 35, 0.7),
    WellTraceTagSpec("PressureC", "Pressure C", "psi", "Float4", "pressure", "Pressure", "psi", 0, 1200, 165, 22, 1.4),
    WellTraceTagSpec("Inventory", "Inventory", "bbl", "Float4", "inventory", "Inventory", "bbl", None, None, 310, 80, 0.2),
    WellTraceTagSpec("PercentFull", "Percent Full", "%", "Float4", "percent", "Percent", "%", 0, 100, 58, 18, 0.4),
    WellTraceTagSpec("Rate", "Rate", "bbl/d", "Float4", "rate", "Rate", "bbl/d", None, None, 235, 38, 1.1),
    WellTraceTagSpec("PercentCut", "Percent Cut", "%", "Float4", "percent", "Percent", "%", 0, 100, 32, 7, 2.0),
    WellTraceTagSpec("Temperature", "Temperature", "degF", "Float4", "temperature", "Temperature", "degF", None, None, 118, 9, 2.8),
)


def navigation_wells(*, limit: int | None = None) -> list[NavigationOption]:
    wells = sqlite_options("well", {})
    return wells[:limit] if limit else wells


def well_profile_key(well_id: str) -> str:
    return f"{WELL_TRACE_PROFILE_PREFIX}-{well_id}"


def well_folder(well: NavigationOption) -> str:
    return f"{WELL_TRACE_ROOT}/{well.value}-{slug(well.label)}"


def seed_nav_well_trace_config(
    *,
    limit: int | None = None,
    provider: str = WELL_TRACE_PROVIDER,
    seed_cache: bool = True,
    window_minutes: int = WELL_TRACE_WINDOW_MINUTES,
) -> dict[str, int]:
    wells = navigation_wells(limit=limit)
    schedule, _created = TagSchedule.objects.update_or_create(
        name=WELL_TRACE_SCHEDULE,
        defaults={"interval_seconds": 60, "enabled": True},
    )
    profile_count = 0
    signal_count = 0
    tag_count = 0
    with transaction.atomic():
        for well_index, well in enumerate(wells, start=1):
            profile, _created = TraceProfile.objects.update_or_create(
                key=well_profile_key(well.value),
                defaults={
                    "label": well.label,
                    "enabled": True,
                    "cache_enabled": True,
                    "cache_window_minutes": window_minutes,
                    "sync_interval_seconds": 60,
                    "history_provider": WELL_TRACE_HISTORY_PROVIDER,
                    "max_query_points": 100_000,
                },
            )
            profile_count += 1
            runtime_tags = []
            for tag_index, spec in enumerate(WELL_TRACE_TAGS, start=1):
                runtime_tag, _created = RuntimeTag.objects.update_or_create(
                    provider=provider,
                    path=f"{well_folder(well)}/{spec.name}",
                    defaults={
                        "display_name": spec.label,
                        "asset_name": well.label,
                        "engineering_units": spec.unit,
                        "schedule": schedule,
                        "enabled": True,
                    },
                )
                runtime_tags.append(runtime_tag)
                tag_count += 1
                TraceSignal.objects.update_or_create(
                    profile=profile,
                    tag=runtime_tag,
                    defaults={
                        "label": spec.label,
                        "unit": spec.unit,
                        "axis_key": spec.axis_key,
                        "axis_label": spec.axis_label,
                        "axis_unit": spec.axis_unit,
                        "range_min": spec.range_min,
                        "range_max": spec.range_max,
                        "sort_order": tag_index,
                        "default_visible": True,
                        "cache_enabled": True,
                    },
                )
                signal_count += 1
            profile.signals.exclude(tag__in=runtime_tags).delete()
            if seed_cache:
                seed_profile_cache(profile, well_index=well_index, window_minutes=window_minutes)
    return {"wells": len(wells), "profiles": profile_count, "tags": tag_count, "signals": signal_count}


def configure_nav_well_ignition_tags(fx: Any, *, limit: int | None = None, provider: str = WELL_TRACE_PROVIDER) -> int:
    configs = [
        {
            "name": well_folder(well),
            "tagType": "Folder",
            "tags": [memory_tag_config(spec, well_index=index_from_well(well)) for spec in WELL_TRACE_TAGS],
        }
        for well in navigation_wells(limit=limit)
    ]
    if configs:
        fx.tag.configure(configs, base_path=f"[{provider}]", collision_policy="o")
    return len(configs) * len(WELL_TRACE_TAGS)


def inject_nav_well_history(
    fx: Any,
    *,
    limit: int | None = None,
    provider: str = WELL_TRACE_PROVIDER,
    history_provider: str = WELL_TRACE_HISTORY_PROVIDER,
    window_minutes: int = WELL_TRACE_WINDOW_MINUTES,
    batch_size: int = 5000,
) -> int:
    end = timezone.now().replace(second=0, microsecond=0)
    start = end - timezone.timedelta(minutes=window_minutes)
    paths: list[str] = []
    values: list[float] = []
    timestamps: list[int] = []
    qualities: list[int] = []
    written = 0
    for well_index, well in enumerate(navigation_wells(limit=limit), start=1):
        folder = well_folder(well)
        for minute in range(window_minutes):
            timestamp_ms = int((start + timezone.timedelta(minutes=minute)).timestamp() * 1000)
            for spec in WELL_TRACE_TAGS:
                paths.append(historical_path(provider=provider, folder=folder, tag_name=spec.name, history_provider=history_provider))
                values.append(well_trace_value(spec, minute, well_index=well_index))
                timestamps.append(timestamp_ms)
                qualities.append(192)
                if len(paths) >= batch_size:
                    fx.historian.store_data_points(paths, values, timestamps=timestamps, qualities=qualities)
                    written += len(paths)
                    paths, values, timestamps, qualities = [], [], [], []
    if paths:
        fx.historian.store_data_points(paths, values, timestamps=timestamps, qualities=qualities)
        written += len(paths)
    return written


def update_nav_well_live_values(
    fx: Any,
    *,
    limit: int | None = None,
    provider: str = WELL_TRACE_PROVIDER,
    history_provider: str = WELL_TRACE_HISTORY_PROVIDER,
    at_time=None,
) -> int:
    at_time = (at_time or timezone.now()).replace(second=0, microsecond=0)
    start_time = live_backfill_start(limit=limit) or at_time
    tag_paths: list[str] = []
    tag_values: list[float] = []
    history_paths: list[str] = []
    history_values: list[float] = []
    timestamps: list[int] = []
    qualities: list[int] = []
    for well_index, well in enumerate(navigation_wells(limit=limit), start=1):
        folder = well_folder(well)
        for spec in WELL_TRACE_TAGS:
            tag_paths.append(tag_path(provider=provider, folder=folder, tag_name=spec.name))
            tag_values.append(well_trace_value(spec, int(at_time.timestamp() // 60), well_index=well_index))
            current = start_time
            while current <= at_time:
                history_paths.append(historical_path(provider=provider, folder=folder, tag_name=spec.name, history_provider=history_provider))
                history_values.append(well_trace_value(spec, int(current.timestamp() // 60), well_index=well_index))
                timestamps.append(int(current.timestamp() * 1000))
                qualities.append(192)
                current += timezone.timedelta(minutes=1)
    if not tag_values:
        return 0
    fx.tag.write_blocking(tag_paths, tag_values)
    if history_values:
        fx.historian.store_data_points(history_paths, history_values, timestamps=timestamps, qualities=qualities)
    return len(history_values)


def live_backfill_start(*, limit: int | None = None):
    keys = [well_profile_key(well.value) for well in navigation_wells(limit=limit)]
    latest = TraceCacheCursor.objects.filter(signal__profile__key__in=keys, last_timestamp__isnull=False).order_by("last_timestamp").values_list("last_timestamp", flat=True).first()
    return latest.replace(second=0, microsecond=0) + timezone.timedelta(minutes=1) if latest else None


def clear_nav_well_cache(*, limit: int | None = None) -> int:
    keys = [well_profile_key(well.value) for well in navigation_wells(limit=limit)]
    deleted_points, _details = TraceCachePoint.objects.filter(signal__profile__key__in=keys).delete()
    TraceCacheCursor.objects.filter(signal__profile__key__in=keys).delete()
    return deleted_points


def sync_nav_well_trace_cache(fx: Any, *, limit: int | None = None, force: bool = False) -> TraceCacheSyncResult:
    profiles = [well_profile_key(well.value) for well in navigation_wells(limit=limit)]
    profile_count = 0
    signal_count = 0
    point_count = 0
    for profile_key in profiles:
        result = sync_trace_cache(fx, profile_key=profile_key, force=force)
        profile_count += result.profile_count
        signal_count += result.signal_count
        point_count += result.point_count
    return TraceCacheSyncResult(profile_count=profile_count, signal_count=signal_count, point_count=point_count)


def seed_profile_cache(profile: TraceProfile, *, well_index: int, window_minutes: int = WELL_TRACE_WINDOW_MINUTES) -> int:
    end = timezone.now().replace(second=0, microsecond=0)
    start = end - timezone.timedelta(minutes=window_minutes)
    signals = list(profile.signals.select_related("tag").order_by("sort_order"))
    points = []
    for minute in range(window_minutes):
        timestamp = start + timezone.timedelta(minutes=minute)
        for signal, spec in zip(signals, WELL_TRACE_TAGS, strict=True):
            points.append(
                TraceCachePoint(
                    signal=signal,
                    timestamp=timestamp,
                    value_float=well_trace_value(spec, minute, well_index=well_index),
                    quality_code="Good",
                )
            )
    TraceCachePoint.objects.bulk_create(
        points,
        batch_size=5000,
        update_conflicts=True,
        update_fields=["value_float", "quality_code", "updated_at"],
        unique_fields=["signal", "timestamp"],
    )
    for signal in signals:
        TraceCacheCursor.objects.update_or_create(
            signal=signal,
            defaults={"last_timestamp": end - timezone.timedelta(minutes=1), "last_sync_at": timezone.now(), "last_error": ""},
        )
    return len(points)


def memory_tag_config(spec: WellTraceTagSpec, *, well_index: int) -> dict[str, Any]:
    return {
        "name": spec.name,
        "tagType": "AtomicTag",
        "valueSource": "memory",
        "dataType": spec.data_type,
        "value": well_trace_value(spec, WELL_TRACE_WINDOW_MINUTES - 1, well_index=well_index),
    }


def well_trace_value(spec: WellTraceTagSpec, minute: int, *, well_index: int) -> float:
    offset = well_index - 1
    daily = math.sin((minute / 1440) * math.tau + spec.phase + offset * 0.017)
    fast = math.sin((minute / 180) + spec.phase + offset * 0.031)
    value = spec.base + (offset % 37) * spec.amplitude * 0.01 + spec.amplitude * daily + spec.amplitude * 0.18 * fast
    if spec.range_min is not None:
        value = max(spec.range_min, value)
    if spec.range_max is not None:
        value = min(spec.range_max, value)
    return round(value, 3)


def index_from_well(well: NavigationOption) -> int:
    try:
        return int(well.value)
    except ValueError:
        return abs(hash(well.value)) % 10_000


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")[:80]


def profile_for_well_index(set_index: int):
    profiles = TraceProfile.objects.filter(key__startswith=f"{WELL_TRACE_PROFILE_PREFIX}-", enabled=True).order_by("id")
    profile_count = profiles.count()
    if not profile_count:
        return None, None, 0, 1
    active_index = max(1, min(profile_count, set_index))
    profile = profiles[active_index - 1]
    well = NavigationOption(value=profile.key.removeprefix(f"{WELL_TRACE_PROFILE_PREFIX}-"), label=profile.label)
    return profile, well, profile_count, active_index


def seeded_well_profiles() -> list[TraceProfile]:
    return list(TraceProfile.objects.filter(key__startswith=f"{WELL_TRACE_PROFILE_PREFIX}-", enabled=True).order_by("id"))


def seeded_navigation_wells() -> list[NavigationOption]:
    profile_keys = set(
        TraceProfile.objects.filter(key__startswith=f"{WELL_TRACE_PROFILE_PREFIX}-", enabled=True).values_list("key", flat=True)
    )
    return [well for well in navigation_wells() if well_profile_key(well.value) in profile_keys]
