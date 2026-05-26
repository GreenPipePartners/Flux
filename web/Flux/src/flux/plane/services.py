from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from django.utils import timezone

from flux.base.runtime import DailyTagExtreme, RuntimeTag, TagSample
from flux.base.models import Entity, Tag, entity_key_hash
from flux.plane.models import Latest, Sample, Series, WindowStat
from flux.status.models import LatestStatus
from flux.status.services import LatestStatusUpdate, bulk_upsert_latest_status


BATCH_SIZE = 5000


@dataclass(frozen=True)
class RuntimePlaneSample:
    tag: RuntimeTag
    value: Any
    quality_code: str
    value_timestamp: Any
    read_at: Any


def ensure_entity(*, kind: str, natural_key: str, display_name: str) -> Entity:
    key_hash = entity_key_hash(kind, natural_key)
    entity, _created = Entity.objects.update_or_create(
        kind=kind,
        natural_key_hash=key_hash,
        defaults={"natural_key": natural_key, "display_name": display_name[:255]},
    )
    return entity


def ensure_series_for_full_path(full_path: str) -> Series:
    provider, tagpath = parse_full_tag_path(full_path)
    tag_name = tagpath.rstrip("/").rsplit("/", 1)[-1]
    base_tag = ensure_base_tag(provider=provider, tagpath=tagpath, name=tag_name)
    return ensure_series_for_base_tag(base_tag)


def ensure_base_tag(*, provider: str, tagpath: str, name: str = "", data_type: str = "", update_rate_ms: int = 1000) -> Tag:
    full_path = tag_full_path(provider, tagpath)
    entity = ensure_entity(kind=Entity.Kind.BASE_TAG, natural_key=full_path, display_name=name or full_path)
    base_tag, _created = Tag.objects.update_or_create(
        provider=provider,
        tagpath=tagpath,
        defaults={
            "entity": entity,
            "full_path": full_path,
            "name": name or tagpath.rsplit("/", 1)[-1],
            "data_type": data_type,
            "update_rate_ms": update_rate_ms if isinstance(update_rate_ms, int) and update_rate_ms > 0 else 1000,
            "enabled": True,
        },
    )
    if base_tag.entity_id is None:
        base_tag.entity = entity
        base_tag.save(update_fields=["entity", "updated_at"])
    return base_tag


def ensure_series_for_base_tag(base_tag: Tag) -> Series:
    entity = ensure_entity(kind=Entity.Kind.PLANE_SERIES, natural_key=base_tag.full_path, display_name=base_tag.name)
    series, _created = Series.objects.update_or_create(
        base_tag=base_tag,
        defaults={
            "entity": entity,
            "enabled": base_tag.enabled,
            "latest_enabled": True,
            "history_enabled": True,
            "sample_interval_ms": base_tag.update_rate_ms,
            "storage_key": base_tag.full_path,
        },
    )
    if series.entity_id is None:
        series.entity = entity
        series.save(update_fields=["entity", "updated_at"])
    return series


def mirror_runtime_samples_to_plane(samples: Iterable[RuntimePlaneSample], *, now=None) -> int:
    runtime_samples = list(samples)
    if not runtime_samples:
        return 0
    now = now or timezone.now()
    runtime_tags = [sample.tag for sample in runtime_samples]
    series_by_full_path = series_for_runtime_tags(runtime_tags)
    latest_rows = []
    sample_rows = []
    status_updates = []
    for sample in runtime_samples:
        series = series_by_full_path.get(sample.tag.full_path)
        if series is None:
            continue
        latest_rows.append(
            Latest(
                series=series,
                value=sample.value,
                quality_code=sample.quality_code,
                value_timestamp=sample.value_timestamp,
                read_at=sample.read_at,
            )
        )
        numeric = numeric_value(sample.value)
        if numeric is not None:
            sample_rows.append(
                Sample(
                    series=series,
                    timestamp=sample.read_at,
                    value_float=numeric,
                    quality_code=sample.quality_code,
                )
            )
        status_updates.append(quality_status_for_sample(series, sample))
    if latest_rows:
        Latest.objects.bulk_create(
            latest_rows,
            update_conflicts=True,
            unique_fields=["series"],
            update_fields=["value", "quality_code", "value_timestamp", "read_at", "updated_at"],
            batch_size=BATCH_SIZE,
        )
    if sample_rows:
        Sample.objects.bulk_create(
            sample_rows,
            update_conflicts=True,
            unique_fields=["series", "timestamp"],
            update_fields=["value_float", "quality_code", "updated_at"],
            batch_size=BATCH_SIZE,
        )
    bulk_upsert_latest_status(status_updates, batch_size=BATCH_SIZE)
    recompute_window_stats_for_runtime_tags(runtime_tags, now=now)
    return len(latest_rows)


def series_for_runtime_tags(runtime_tags: Iterable[RuntimeTag]) -> dict[str, Series]:
    tags = list(runtime_tags)
    full_paths = [tag.full_path for tag in tags]
    series_by_full_path = {
        series.base_tag.full_path: series
        for series in Series.objects.select_related("base_tag", "entity").filter(base_tag__full_path__in=full_paths)
    }
    for tag in tags:
        if tag.full_path not in series_by_full_path:
            series_by_full_path[tag.full_path] = ensure_series_for_full_path(tag.full_path)
    return series_by_full_path


def quality_status_for_sample(series: Series, sample: RuntimePlaneSample) -> LatestStatusUpdate:
    good = sample.quality_code.lower() == "good"
    return LatestStatusUpdate(
        entity=series.entity,
        status_kind=LatestStatus.StatusKind.QUALITY,
        observed_state=LatestStatus.ObservedState.OK if good else LatestStatus.ObservedState.ERROR,
        severity=LatestStatus.Severity.OK if good else LatestStatus.Severity.ERROR,
        summary="Good quality sample." if good else "Bad quality sample: %s" % sample.quality_code,
        source="flux.opt.sampler",
        source_instance="runtime",
        last_seen_at=sample.read_at,
        evidence={
            "series_id": series.id,
            "base_tag_id": series.base_tag_id,
            "quality_code": sample.quality_code,
            "value_timestamp": sample.value_timestamp.isoformat() if sample.value_timestamp else None,
        },
    )


def recompute_window_stats_for_runtime_tags(runtime_tags: Iterable[RuntimeTag], *, now=None) -> int:
    tags = list({tag.id: tag for tag in runtime_tags}.values())
    if not tags:
        return 0
    now = now or timezone.now()
    series_by_full_path = series_for_runtime_tags(tags)
    series_by_tag_id = {
        tag.id: series_by_full_path[tag.full_path]
        for tag in tags
        if tag.full_path in series_by_full_path
    }
    if not series_by_tag_id:
        return 0
    windows = runtime_window_values([tag.id for tag in tags], now=now)
    today = timezone.localdate(now)
    rows = []
    for tag_id, by_window in windows.items():
        series = series_by_tag_id.get(tag_id)
        if series is None:
            continue
        for window, values in by_window.items():
            start = window_start(today, window)
            rows.append(
                WindowStat(
                    series=series,
                    window=window,
                    min_value=values["min"],
                    max_value=values["max"],
                    sample_count=values["count"],
                    window_start=start,
                    window_end=now,
                    computed_at=now,
                )
            )
    if not rows:
        return 0
    WindowStat.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["series", "window"],
        update_fields=[
            "min_value",
            "max_value",
            "sample_count",
            "window_start",
            "window_end",
            "computed_at",
            "updated_at",
        ],
        batch_size=BATCH_SIZE,
    )
    return len(rows)


def runtime_window_values(tag_ids: list[int], *, now) -> dict[int, dict[str, dict[str, float | int]]]:
    today = timezone.localdate(now)
    today_start = aware_midnight(today)
    start_30 = today - timedelta(days=29)
    by_tag: dict[int, dict[str, dict[str, float | int]]] = defaultdict(dict)
    today_extremes = sample_extremes(
        TagSample.objects.filter(tag_id__in=tag_ids, read_at__gte=today_start, read_at__lte=now).values_list(
            "tag_id", "value"
        )
    )
    for tag_id, values in today_extremes.items():
        merge_values(by_tag[tag_id], WindowStat.Window.TODAY, values["min"], values["max"], values["count"])
        merge_values(by_tag[tag_id], WindowStat.Window.ROLLING_7D, values["min"], values["max"], values["count"])
        merge_values(by_tag[tag_id], WindowStat.Window.ROLLING_30D, values["min"], values["max"], values["count"])
    daily_rows = DailyTagExtreme.objects.filter(
        tag_id__in=tag_ids,
        date__gte=start_30,
        date__lt=today,
    ).values_list("tag_id", "date", "min_value", "max_value", "sample_count")
    for tag_id, row_date, min_value, max_value, sample_count in daily_rows:
        age_days = (today - row_date).days
        if age_days < 7:
            merge_values(by_tag[tag_id], WindowStat.Window.ROLLING_7D, min_value, max_value, sample_count)
        if age_days < 30:
            merge_values(by_tag[tag_id], WindowStat.Window.ROLLING_30D, min_value, max_value, sample_count)
    return by_tag


def sample_extremes(rows) -> dict[int, dict[str, float | int]]:
    extremes: dict[int, dict[str, float | int]] = {}
    for tag_id, value in rows:
        numeric = numeric_value(value)
        if numeric is None:
            continue
        if tag_id not in extremes:
            extremes[tag_id] = {"min": numeric, "max": numeric, "count": 1}
            continue
        values = extremes[tag_id]
        values["min"] = min(values["min"], numeric)
        values["max"] = max(values["max"], numeric)
        values["count"] += 1
    return extremes


def merge_values(window_values: dict[str, dict[str, float | int]], window: str, min_value: float, max_value: float, count: int) -> None:
    if window not in window_values:
        window_values[window] = {"min": min_value, "max": max_value, "count": count}
        return
    values = window_values[window]
    values["min"] = min(values["min"], min_value)
    values["max"] = max(values["max"], max_value)
    values["count"] += count


def numeric_value(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def window_start(today: date, window: str):
    if window == WindowStat.Window.TODAY:
        return aware_midnight(today)
    if window == WindowStat.Window.ROLLING_7D:
        return aware_midnight(today - timedelta(days=6))
    return aware_midnight(today - timedelta(days=29))


def aware_midnight(day: date):
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


def parse_full_tag_path(full_path: str) -> tuple[str, str]:
    match = re.fullmatch(r"\[([^\]]+)](.+)", full_path.strip())
    if not match:
        raise ValueError(f"tag reference must use full [provider]path form: {full_path}")
    provider, tagpath = match.groups()
    return provider, tagpath.strip("/")


def tag_full_path(provider: str, tagpath: str) -> str:
    return "[%s]%s" % (provider, tagpath) if tagpath else "[%s]" % provider
