from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flux.base.runtime import TagSample


@dataclass(frozen=True)
class TraceSeries:
    tag_id: int
    name: str
    full_path: str
    x: list[str]
    y: list[float]


def trace_sample_series(
    *, max_tags: int = 3, samples_per_tag: int = 500, since=None
) -> dict[str, list[dict[str, Any]]]:
    rows = TagSample.objects.select_related("tag")
    if since is not None:
        rows = rows.filter(read_at__gt=since)
    rows = rows.order_by("-read_at")[: max_tags * samples_per_tag * 4]
    series_by_tag: dict[int, TraceSeries] = {}
    latest_read_at: str | None = None

    for sample in rows:
        value = _numeric_value(sample.value)
        if value is None:
            continue
        read_at = sample.read_at.isoformat()
        if latest_read_at is None or read_at > latest_read_at:
            latest_read_at = read_at
        tag_id = sample.tag_id
        if tag_id not in series_by_tag:
            if len(series_by_tag) >= max_tags:
                continue
            series_by_tag[tag_id] = TraceSeries(
                tag_id=sample.tag_id,
                name=sample.tag.display_name,
                full_path=sample.tag.full_path,
                x=[],
                y=[],
            )

        series = series_by_tag[tag_id]
        if len(series.x) >= samples_per_tag:
            continue
        series.x.append(read_at)
        series.y.append(value)

    return {
        "series": [
            {
                "tagId": series.tag_id,
                "name": series.name,
                "fullPath": series.full_path,
                "x": list(reversed(series.x)),
                "y": list(reversed(series.y)),
            }
            for series in series_by_tag.values()
        ],
        "latestReadAt": latest_read_at,
    }


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None
