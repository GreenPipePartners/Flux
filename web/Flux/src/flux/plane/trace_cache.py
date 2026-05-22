from __future__ import annotations

from django.db import transaction

from flux.base.runtime import TagSample
from flux.trace.models import TraceCachePoint, TraceProfile


def seed_trace_cache_from_runtime_history(profile: TraceProfile, *, sample_limit: int | None = 48, batch_size: int = 5000) -> int:
    """Seed local trace cache points from RuntimeTag sample history for a trace profile."""
    total = 0
    points = []
    for signal in profile.signals.select_related("tag"):
        seen_timestamps = set()
        samples = TagSample.objects.filter(tag=signal.tag).order_by("-read_at")
        if sample_limit is not None:
            samples = samples[:sample_limit]
        for sample in samples:
            if isinstance(sample.value, bool) or not isinstance(sample.value, int | float):
                continue
            timestamp = sample.read_at.replace(second=0, microsecond=0)
            if timestamp in seen_timestamps:
                continue
            seen_timestamps.add(timestamp)
            points.append(
                TraceCachePoint(
                    signal=signal,
                    timestamp=timestamp,
                    value_float=float(sample.value),
                    quality_code=sample.quality_code,
                )
            )
            if len(points) >= batch_size:
                total += bulk_upsert_trace_cache_points(points, batch_size=batch_size)
                points = []
    if points:
        total += bulk_upsert_trace_cache_points(points, batch_size=batch_size)
    return total


def bulk_upsert_trace_cache_points(points: list[TraceCachePoint], *, batch_size: int) -> int:
    with transaction.atomic():
        TraceCachePoint.objects.bulk_create(
            points,
            batch_size=batch_size,
            update_conflicts=True,
            update_fields=["value_float", "quality_code", "updated_at"],
            unique_fields=["signal", "timestamp"],
        )
    return len(points)
