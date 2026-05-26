from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Max
from django.utils import timezone

from flux.plane.models import Sample, Series


@dataclass(frozen=True)
class PlaneSample:
    tag_id: int | None
    series_id: int | None
    name: str
    full_path: str
    storage_key: str
    unit: str
    value: Any
    read_at: Any


@dataclass(frozen=True)
class PlaneSampleQueryResult:
    samples: list[PlaneSample]
    source: str = "plane-samples"


def recent_sample_queryset():
    return Sample.objects.select_related("series", "series__base_tag").prefetch_related("series__chart_signals__profile", "series__chart_signals__tag").order_by("-timestamp")


def recent_series_samples(
    *,
    max_series: int = 8,
    samples_per_series: int = 5760,
    since=None,
    window_days: int | None = 4,
    asset_name: str = "",
) -> PlaneSampleQueryResult:
    rows = Sample.objects.select_related("series", "series__base_tag").prefetch_related("series__chart_signals__tag")
    if asset_name:
        rows = rows.filter(series__chart_signals__tag__asset_name=asset_name).distinct()
    if since is None and window_days is not None:
        latest_read_at = rows.aggregate(latest=Max("timestamp"))["latest"]
        since = latest_read_at - timezone.timedelta(days=window_days) if latest_read_at else timezone.now() - timezone.timedelta(days=window_days)
    if since is not None:
        rows = rows.filter(timestamp__gt=since)
    sample_rows = list(rows.order_by("-timestamp")[: max_series * samples_per_series])
    return PlaneSampleQueryResult(
        samples=[plane_sample_from_plane_row(row) for row in sample_rows],
    )


def plane_sample_from_plane_row(sample: Sample) -> PlaneSample:
    signal = first_chart_signal(sample.series)
    storage_key = sample.series.storage_key or sample.series.base_tag.full_path
    return PlaneSample(
        tag_id=signal.tag_id if signal is not None else None,
        series_id=sample.series_id,
        name=sample.series.base_tag.name,
        full_path=storage_key,
        storage_key=storage_key,
        unit=signal.display_unit if signal is not None else "",
        value=sample.value_float,
        read_at=sample.timestamp,
    )


def first_chart_signal(series: Series):
    signals = list(series.chart_signals.all())
    return signals[0] if signals else None
