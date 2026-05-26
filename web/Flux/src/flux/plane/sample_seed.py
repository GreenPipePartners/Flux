from __future__ import annotations

from django.db import transaction

from flux.base.runtime import TagSample
from flux.plane.models import Sample
from flux.plane.services import ensure_series_for_full_path
from flux.trace.models import TraceProfile, TraceSignal


def seed_plane_samples_from_runtime_history(profile: TraceProfile, *, sample_limit: int | None = 48, batch_size: int = 5000) -> int:
    """Seed Plane samples from legacy RuntimeTag sample history for a trace profile."""
    total = 0
    points = []
    for signal in profile.signals.select_related("tag", "series"):
        ensure_signal_series(signal)
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
                Sample(
                    series_id=signal.series_id,
                    timestamp=timestamp,
                    value_float=float(sample.value),
                    quality_code=sample.quality_code,
                )
            )
            if len(points) >= batch_size:
                total += bulk_upsert_plane_samples(points, batch_size=batch_size)
                points = []
    if points:
        total += bulk_upsert_plane_samples(points, batch_size=batch_size)
    return total


def bulk_upsert_plane_samples(points: list[Sample], *, batch_size: int) -> int:
    with transaction.atomic():
        Sample.objects.bulk_create(
            points,
            batch_size=batch_size,
            update_conflicts=True,
            update_fields=["value_float", "quality_code", "updated_at"],
            unique_fields=["series", "timestamp"],
        )
    return len(points)


def ensure_signal_series(signal: TraceSignal) -> None:
    if signal.series_id is not None:
        return
    signal.series = ensure_series_for_full_path(signal.tag.full_path)
    signal.save(update_fields=["series", "updated_at"])
