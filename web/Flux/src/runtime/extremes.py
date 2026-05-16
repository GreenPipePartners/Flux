from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from flux.base.runtime import DailyTagExtreme, RuntimeTag, TagSample


@dataclass(frozen=True)
class Extreme:
    min_value: float
    max_value: float


def rollup_daily_extremes(*, day: date | None = None) -> int:
    day = day or (timezone.localdate() - timedelta(days=1))
    start = _aware_midnight(day)
    end = _aware_midnight(day + timedelta(days=1))
    extremes = _sample_extremes(
        TagSample.objects.filter(read_at__gte=start, read_at__lt=end).values_list("tag_id", "value")
    )
    with transaction.atomic():
        for tag_id, values in extremes.items():
            DailyTagExtreme.objects.update_or_create(
                tag_id=tag_id,
                date=day,
                defaults={
                    "min_value": values["min"],
                    "max_value": values["max"],
                    "sample_count": values["count"],
                },
            )
    return len(extremes)


def rolling_midnight_extremes(tags: Iterable[RuntimeTag], *, now=None) -> dict[int, dict[int, Extreme]]:
    tag_ids = [tag.id for tag in tags]
    if not tag_ids:
        return {}

    now = now or timezone.now()
    today = timezone.localdate(now)
    today_start = _aware_midnight(today)
    start_30 = today - timedelta(days=29)
    by_tag: dict[int, dict[int, dict[str, float | int]]] = defaultdict(dict)

    today_extremes = _sample_extremes(
        TagSample.objects.filter(tag_id__in=tag_ids, read_at__gte=today_start, read_at__lte=now).values_list(
            "tag_id", "value"
        )
    )
    for tag_id, values in today_extremes.items():
        for days in (1, 7, 30):
            _merge_values(by_tag[tag_id], days, values["min"], values["max"])

    daily_rows = DailyTagExtreme.objects.filter(
        tag_id__in=tag_ids,
        date__gte=start_30,
        date__lt=today,
    ).values_list("tag_id", "date", "min_value", "max_value")
    for tag_id, row_date, min_value, max_value in daily_rows:
        age_days = (today - row_date).days
        for days in (7, 30):
            if age_days < days:
                _merge_values(by_tag[tag_id], days, min_value, max_value)

    return {
        tag_id: {
            days: Extreme(min_value=values["min"], max_value=values["max"])
            for days, values in windows.items()
        }
        for tag_id, windows in by_tag.items()
    }


def _sample_extremes(rows) -> dict[int, dict[str, float | int]]:
    extremes: dict[int, dict[str, float | int]] = {}
    for tag_id, value in rows:
        numeric = _numeric_value(value)
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


def _merge_values(window_values: dict[int, dict[str, float | int]], days: int, min_value: float, max_value: float) -> None:
    if days not in window_values:
        window_values[days] = {"min": min_value, "max": max_value}
        return
    values = window_values[days]
    values["min"] = min(values["min"], min_value)
    values["max"] = max(values["max"], max_value)


def _numeric_value(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _aware_midnight(day: date):
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())
