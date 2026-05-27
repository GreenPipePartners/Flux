from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta, timezone as datetime_timezone

import psycopg
from django.utils import timezone

from flux.plane.models import Sample, Series


QUESTDB_DSN = os.getenv("QUESTDB_DSN", "postgresql://admin:quest@localhost:8812/qdb")
QUESTDB_PLANE_SAMPLE_TABLE = "plane_samples"


@dataclass(frozen=True)
class QuestDBWindowStat:
    window: str
    min_value: float
    max_value: float
    sample_count: int


def questdb_connect():
    return psycopg.connect(os.getenv("QUESTDB_DSN", QUESTDB_DSN), autocommit=True, connect_timeout=1)


def ensure_questdb_schema(*, replace: bool = False) -> None:
    with questdb_connect() as connection:
        with connection.cursor() as cursor:
            if replace:
                cursor.execute(f"DROP TABLE IF EXISTS {QUESTDB_PLANE_SAMPLE_TABLE}")
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {QUESTDB_PLANE_SAMPLE_TABLE} (
                    series_id LONG,
                    storage_key SYMBOL INDEX,
                    ts TIMESTAMP,
                    value DOUBLE,
                    quality SYMBOL
                ) timestamp(ts) PARTITION BY DAY WAL
                """
            )


def export_series_samples_to_questdb(*, series_ids: list[int], replace: bool = False, batch_size: int = 5000) -> int:
    ensure_questdb_schema(replace=replace)
    series_by_id = {series.id: series for series in Series.objects.select_related("base_tag").filter(id__in=series_ids)}
    latest_by_series = {} if replace else questdb_latest_timestamps_by_series([*series_by_id])
    total = 0
    rows = incremental_plane_sample_rows(series_by_id=series_by_id, latest_by_series=latest_by_series, batch_size=batch_size)
    with questdb_connect() as connection:
        with connection.cursor() as cursor:
            batch = []
            for series_id, storage_key, timestamp, value, quality in rows:
                batch.append((series_id, storage_key, timestamp, value, quality or "Good"))
                if len(batch) >= batch_size:
                    cursor.executemany(
                        f"INSERT INTO {QUESTDB_PLANE_SAMPLE_TABLE} (series_id, storage_key, ts, value, quality) VALUES (%s, %s, %s, %s, %s)",
                        batch,
                    )
                    total += len(batch)
                    batch = []
            if batch:
                cursor.executemany(
                    f"INSERT INTO {QUESTDB_PLANE_SAMPLE_TABLE} (series_id, storage_key, ts, value, quality) VALUES (%s, %s, %s, %s, %s)",
                    batch,
                )
                total += len(batch)
    return total


def incremental_plane_sample_rows(*, series_by_id: dict[int, Series], latest_by_series: dict[int, object], batch_size: int):
    for series_id, series in series_by_id.items():
        queryset = Sample.objects.filter(series_id=series_id).order_by("timestamp")
        latest = latest_by_series.get(series_id)
        if latest is not None:
            queryset = queryset.filter(timestamp__gt=latest)
        for timestamp, value, quality in queryset.values_list("timestamp", "value_float", "quality_code").iterator(chunk_size=batch_size):
            yield series_id, series.storage_key or series.base_tag.full_path, timestamp, value, quality


def questdb_latest_timestamps_by_series(series_ids: list[int]) -> dict[int, object]:
    if not series_ids:
        return {}
    placeholders = ",".join(["%s"] * len(series_ids))
    with questdb_connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT series_id, max(ts) FROM {QUESTDB_PLANE_SAMPLE_TABLE} WHERE series_id IN ({placeholders}) GROUP BY series_id",
                series_ids,
            )
            return {int(series_id): questdb_utc(latest) for series_id, latest in cursor.fetchall() if latest is not None}


def questdb_window_stats_by_series(series_ids: list[int], *, now=None) -> dict[int, dict[str, QuestDBWindowStat]]:
    if not series_ids:
        return {}
    now = now or timezone.now()
    unique_series_ids = sorted(set(series_ids))
    by_series: dict[int, dict[str, QuestDBWindowStat]] = {series_id: {} for series_id in unique_series_ids}
    windows = (
        ("today", now - timedelta(days=1)),
        ("rolling_7d", now - timedelta(days=7)),
        ("rolling_30d", now - timedelta(days=30)),
    )
    with questdb_connect() as connection:
        with connection.cursor() as cursor:
            for window, start in windows:
                for series_id, min_value, max_value, sample_count in questdb_window_rows(
                    cursor,
                    series_ids=unique_series_ids,
                    start=start,
                    end=now,
                ):
                    by_series.setdefault(series_id, {})[window] = QuestDBWindowStat(
                        window=window,
                        min_value=float(min_value),
                        max_value=float(max_value),
                        sample_count=int(sample_count),
                    )
    return {series_id: windows for series_id, windows in by_series.items() if windows}


def questdb_window_rows(cursor, *, series_ids: list[int], start, end):
    placeholders = ",".join(["%s"] * len(series_ids))
    cursor.execute(
        f"""
        SELECT series_id, min(value), max(value), count()
        FROM {QUESTDB_PLANE_SAMPLE_TABLE}
        WHERE series_id IN ({placeholders}) AND ts >= %s AND ts <= %s
        GROUP BY series_id
        """,
        [*series_ids, start, end],
    )
    return cursor.fetchall()


def questdb_utc(timestamp):
    if timestamp is None:
        return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=datetime_timezone.utc)
    return timestamp.astimezone(datetime_timezone.utc)
