from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Max
from flux.base.runtime import TagSample
from django.utils import timezone


@dataclass(frozen=True)
class TraceSeries:
    tag_id: int
    name: str
    full_path: str
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
    rows = TagSample.objects.select_related("tag")
    if asset_name:
        rows = rows.filter(tag__asset_name=asset_name)
    if since is None and window_days is not None:
        latest_read_at = rows.aggregate(latest=Max("read_at"))["latest"]
        since = latest_read_at - timezone.timedelta(days=window_days) if latest_read_at else timezone.now() - timezone.timedelta(days=window_days)
    if since is not None:
        rows = rows.filter(read_at__gt=since)
    rows = rows.order_by("-read_at").values(
        "tag_id",
        "tag__display_name",
        "tag__provider",
        "tag__path",
        "tag__engineering_units",
        "value",
        "read_at",
    )[: max_tags * samples_per_tag]
    series_by_tag: dict[int, TraceSeries] = {}
    latest_read_at: str | None = None

    for sample in rows:
        value = _numeric_value(sample["value"])
        if value is None:
            continue
        read_at_dt = sample["read_at"]
        read_at = int(read_at_dt.timestamp())
        if latest_read_at is None or read_at > latest_read_at:
            latest_read_at = read_at
        tag_id = sample["tag_id"]
        if tag_id not in series_by_tag:
            if len(series_by_tag) >= max_tags:
                continue
            display_name = sample["tag__display_name"]
            unit = sample["tag__engineering_units"]
            series_by_tag[tag_id] = TraceSeries(
                tag_id=tag_id,
                name=display_name,
                full_path="[%s]%s" % (sample["tag__provider"], sample["tag__path"]),
                x=[],
                y=[],
                unit=unit,
                axis_key=axis_key_for_tag(display_name, unit),
            )

        series = series_by_tag[tag_id]
        if len(series.x) >= samples_per_tag:
            continue
        series.x.append(read_at)
        series.y.append(value)

    x_values = shared_x(series_by_tag.values(), display_points_per_tag)
    return {
        "x": x_values,
        "series": [
            {
                "rawCount": len(series.x),
                "tagId": series.tag_id,
                "name": series.name,
                "fullPath": series.full_path,
                "unit": series.unit,
                "axisKey": series.axis_key,
                "x": [],
                "y": values_for_shared_x(series, x_values),
            }
            for series in series_by_tag.values()
        ],
        "axisGroups": list(AXIS_GROUPS.values()),
        "latestReadAt": timezone.datetime.fromtimestamp(latest_read_at, tz=timezone.get_current_timezone()).isoformat()
        if latest_read_at is not None
        else None,
        "windowDays": window_days,
        "windowLabel": "%s day%s" % (window_days, "" if window_days == 1 else "s") if window_days is not None else "all history",
        "displayPointsPerTag": display_points_per_tag,
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
