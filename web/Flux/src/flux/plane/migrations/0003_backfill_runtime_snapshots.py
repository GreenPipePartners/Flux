from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db import migrations
from django.utils import timezone


BATCH_SIZE = 5000


def backfill_runtime_snapshots(apps, schema_editor):
    LatestValue = apps.get_model("runtime", "LatestTagValue")
    RuntimeTag = apps.get_model("runtime", "RuntimeTag")
    Series = apps.get_model("plane", "Series")
    Latest = apps.get_model("plane", "Latest")
    WindowStat = apps.get_model("plane", "WindowStat")
    TagSample = apps.get_model("runtime", "TagSample")
    DailyTagExtreme = apps.get_model("runtime", "DailyTagExtreme")

    backfill_latest_values(LatestValue, Series, Latest)
    backfill_window_stats(RuntimeTag, Series, WindowStat, TagSample, DailyTagExtreme)


def backfill_latest_values(LatestValue, Series, Latest):
    pending = []
    for latest in LatestValue.objects.select_related("tag").only(
        "value",
        "quality_code",
        "value_timestamp",
        "read_at",
        "tag__provider",
        "tag__path",
    ).iterator(chunk_size=BATCH_SIZE):
        pending.append(latest)
        if len(pending) >= BATCH_SIZE:
            flush_latest_batch(Series, Latest, pending)
            pending = []
    if pending:
        flush_latest_batch(Series, Latest, pending)


def flush_latest_batch(Series, Latest, latest_values):
    full_paths = {runtime_full_path(latest.tag) for latest in latest_values}
    series_by_path = {
        series.base_tag.full_path: series
        for series in Series.objects.select_related("base_tag").filter(base_tag__full_path__in=full_paths).only("id", "base_tag__full_path")
    }
    rows = []
    for latest in latest_values:
        series = series_by_path.get(runtime_full_path(latest.tag))
        if series is None:
            continue
        rows.append(
            Latest(
                series_id=series.id,
                value=latest.value,
                quality_code=latest.quality_code,
                value_timestamp=latest.value_timestamp,
                read_at=latest.read_at,
            )
        )
    if rows:
        Latest.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["series"],
            update_fields=["value", "quality_code", "value_timestamp", "read_at", "updated_at"],
            batch_size=BATCH_SIZE,
        )


def backfill_window_stats(RuntimeTag, Series, WindowStat, TagSample, DailyTagExtreme):
    pending = []
    for runtime_tag in RuntimeTag.objects.all().only("id", "provider", "path").iterator(chunk_size=BATCH_SIZE):
        pending.append(runtime_tag)
        if len(pending) >= 1000:
            flush_window_batch(Series, WindowStat, TagSample, DailyTagExtreme, pending)
            pending = []
    if pending:
        flush_window_batch(Series, WindowStat, TagSample, DailyTagExtreme, pending)


def flush_window_batch(Series, WindowStat, TagSample, DailyTagExtreme, runtime_tags):
    now = timezone.now()
    series_by_full_path = {
        series.base_tag.full_path: series
        for series in Series.objects.select_related("base_tag").filter(
            base_tag__full_path__in=[runtime_full_path(tag) for tag in runtime_tags]
        ).only("id", "base_tag__full_path")
    }
    series_by_tag_id = {
        tag.id: series_by_full_path[runtime_full_path(tag)]
        for tag in runtime_tags
        if runtime_full_path(tag) in series_by_full_path
    }
    if not series_by_tag_id:
        return
    windows = runtime_window_values(TagSample, DailyTagExtreme, list(series_by_tag_id), now=now)
    today = timezone.localdate(now)
    rows = []
    for tag_id, by_window in windows.items():
        series = series_by_tag_id.get(tag_id)
        if series is None:
            continue
        for window, values in by_window.items():
            rows.append(
                WindowStat(
                    series_id=series.id,
                    window=window,
                    min_value=values["min"],
                    max_value=values["max"],
                    sample_count=values["count"],
                    window_start=window_start(today, window),
                    window_end=now,
                    computed_at=now,
                )
            )
    if rows:
        WindowStat.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["series", "window"],
            update_fields=["min_value", "max_value", "sample_count", "window_start", "window_end", "computed_at", "updated_at"],
            batch_size=BATCH_SIZE,
        )


def runtime_window_values(TagSample, DailyTagExtreme, tag_ids: list[int], *, now) -> dict[int, dict[str, dict[str, float | int]]]:
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
        for window in ("today", "rolling_7d", "rolling_30d"):
            merge_values(by_tag[tag_id], window, values["min"], values["max"], values["count"])
    daily_rows = DailyTagExtreme.objects.filter(
        tag_id__in=tag_ids,
        date__gte=start_30,
        date__lt=today,
    ).values_list("tag_id", "date", "min_value", "max_value", "sample_count")
    for tag_id, row_date, min_value, max_value, sample_count in daily_rows:
        age_days = (today - row_date).days
        if age_days < 7:
            merge_values(by_tag[tag_id], "rolling_7d", min_value, max_value, sample_count)
        if age_days < 30:
            merge_values(by_tag[tag_id], "rolling_30d", min_value, max_value, sample_count)
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


def window_start(today, window: str):
    if window == "today":
        return aware_midnight(today)
    if window == "rolling_7d":
        return aware_midnight(today - timedelta(days=6))
    return aware_midnight(today - timedelta(days=29))


def aware_midnight(day):
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


def runtime_full_path(tag) -> str:
    return "[%s]%s" % (tag.provider, tag.path)


class Migration(migrations.Migration):

    dependencies = [
        ("plane", "0002_backfill_spot_chart_series"),
        ("runtime", "0005_runtimetag_category"),
    ]

    operations = [migrations.RunPython(backfill_runtime_snapshots, migrations.RunPython.noop)]
