from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from flux.plane.samples import recent_series_samples


@dataclass(frozen=True)
class TraceSeries:
    tag_id: int | None
    series_id: int | None
    name: str
    full_path: str
    storage_key: str
    x: list[int]
    y: list[float]
    unit: str
    axis_key: str


AXIS_GROUPS = {
    "pressure": {"key": "pressure", "label": "Pressure", "unit": "psi", "range": [0, 1200], "side": 1},
    "percent": {"key": "percent", "label": "Percent", "unit": "%", "range": [0, 100], "side": 1},
    "process": {"key": "process", "label": "Process", "unit": "mixed", "range": [0, 650], "side": 3},
}


def trace_sample_series(
    *,
    max_tags: int = 8,
    samples_per_tag: int = 5760,
    since=None,
    window_days: int | None = 4,
    asset_name: str = "",
    display_points_per_tag: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    query_result = recent_series_samples(
        max_series=max_tags,
        samples_per_series=samples_per_tag,
        since=since,
        window_days=window_days,
        asset_name=asset_name,
    )
    series_by_key: dict[tuple[str, int], TraceSeries] = {}
    latest_read_at: int | None = None

    for sample in query_result.samples:
        value = _numeric_value(sample.value)
        if value is None:
            continue
        read_at_dt = sample.read_at
        read_at = int(read_at_dt.timestamp())
        if latest_read_at is None or read_at > latest_read_at:
            latest_read_at = read_at
        series_key = ("series", sample.series_id) if sample.series_id is not None else ("tag", sample.tag_id or 0)
        if series_key not in series_by_key:
            if len(series_by_key) >= max_tags:
                continue
            series_by_key[series_key] = TraceSeries(
                tag_id=sample.tag_id,
                series_id=sample.series_id,
                name=sample.name,
                full_path=sample.full_path,
                storage_key=sample.storage_key,
                x=[],
                y=[],
                unit=sample.unit,
                axis_key=axis_key_for_tag(sample.name, sample.unit),
            )

        series = series_by_key[series_key]
        if len(series.x) >= samples_per_tag:
            continue
        series.x.append(read_at)
        series.y.append(value)

    x_values = shared_x(series_by_key.values(), display_points_per_tag)
    return {
        "x": x_values,
        "series": [
            {
                "rawCount": len(series.x),
                "tagId": series.tag_id,
                "seriesId": series.series_id,
                "storageKey": series.storage_key,
                "name": series.name,
                "fullPath": series.full_path,
                "unit": series.unit,
                "axisKey": series.axis_key,
                "x": [],
                "y": values_for_shared_x(series, x_values),
            }
            for series in series_by_key.values()
        ],
        "axisGroups": list(AXIS_GROUPS.values()),
        "latestReadAt": timezone.datetime.fromtimestamp(latest_read_at, tz=timezone.get_current_timezone()).isoformat()
        if latest_read_at is not None
        else None,
        "windowDays": window_days,
        "windowLabel": "%s day%s" % (window_days, "" if window_days == 1 else "s") if window_days is not None else "all history",
        "displayPointsPerTag": display_points_per_tag,
        "source": query_result.source,
    }


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def axis_key_for_tag(name: str, unit: str = "") -> str:
    text = f"{name} {unit}".lower()
    if "pressure" in text or " psi" in text or text.endswith("psi"):
        return "pressure"
    if "%" in text or "percent" in text or "water cut" in text or "full" in text:
        return "percent"
    return "process"


def decimate(values: list[Any], max_points: int | None) -> list[Any]:
    if max_points is None or len(values) <= max_points or max_points < 2:
        return values
    step = (len(values) - 1) / (max_points - 1)
    return [values[round(index * step)] for index in range(max_points)]


def shared_x(series_list, max_points: int | None) -> list[int]:
    values = sorted({time_value for series in series_list for time_value in series.x})
    return decimate(values, max_points)


def values_for_shared_x(series: TraceSeries, x_values: list[int]) -> list[float | None]:
    by_time = {time_value: value for time_value, value in zip(series.x, series.y, strict=True)}
    return [by_time.get(time_value) for time_value in x_values]
