from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from datetime import timedelta, timezone as datetime_timezone

import orjson
import psycopg

from flux.plane.models import Sample
from flux.trace.models import TraceProfile, TraceSignal


QUESTDB_DSN = os.getenv("QUESTDB_DSN", "postgresql://admin:quest@localhost:8812/qdb")
_thread_local = threading.local()
_latest_cache: dict[tuple[int, ...], tuple[float, object]] = {}
_latest_cache_lock = threading.Lock()
_profile_cache: dict[int, tuple[float, dict]] = {}
_profile_cache_lock = threading.Lock()
_LATEST_CACHE_SECONDS = float(os.getenv("QUESTDB_LATEST_CACHE_SECONDS", "30"))
_PROFILE_CACHE_SECONDS = float(os.getenv("QUESTDB_PROFILE_CACHE_SECONDS", "60"))
_request_gate = threading.BoundedSemaphore(int(os.getenv("QUESTDB_TRACE_CONCURRENCY", "8")))
QUESTDB_PLANE_SAMPLE_TABLE = "plane_samples"


def questdb_connect():
    return psycopg.connect(os.getenv("QUESTDB_DSN", QUESTDB_DSN), autocommit=True)


def questdb_thread_connection():
    connection = getattr(_thread_local, "questdb_connection", None)
    if connection is None or connection.closed:
        connection = questdb_connect()
        _thread_local.questdb_connection = connection
    return connection


def reset_questdb_thread_connection() -> None:
    connection = getattr(_thread_local, "questdb_connection", None)
    if connection is not None:
        try:
            connection.close()
        finally:
            _thread_local.questdb_connection = None


@contextmanager
def questdb_cursor(connection=None):
    owned_connection = connection is None
    connection = connection or questdb_thread_connection()
    try:
        with connection.cursor() as cursor:
            yield cursor
    except psycopg.Error:
        if owned_connection:
            try:
                connection.close()
            finally:
                _thread_local.questdb_connection = None
        raise


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


def export_plane_samples_to_questdb(*, profile_keys: list[str], replace: bool = False, batch_size: int = 5000) -> int:
    ensure_questdb_schema(replace=replace)
    series_by_id = {
        signal.series_id: signal.series
        for signal in TraceSignal.objects.select_related("series", "series__base_tag").filter(profile__key__in=profile_keys, series__isnull=False).order_by("series_id")
    }
    latest_by_series = {} if replace else questdb_latest_timestamps_by_series([*series_by_id])
    total = 0
    rows = incremental_plane_sample_rows(series_by_id=series_by_id, latest_by_series=latest_by_series, batch_size=batch_size)
    with questdb_connect() as connection:
        with connection.cursor() as cursor:
            batch = []
            for series_id, storage_key, timestamp, value, quality in rows:
                batch.append((series_id, storage_key, timestamp, value, quality or "Good"))
                if len(batch) >= batch_size:
                    cursor.executemany(f"INSERT INTO {QUESTDB_PLANE_SAMPLE_TABLE} (series_id, storage_key, ts, value, quality) VALUES (%s, %s, %s, %s, %s)", batch)
                    total += len(batch)
                    batch = []
            if batch:
                cursor.executemany(f"INSERT INTO {QUESTDB_PLANE_SAMPLE_TABLE} (series_id, storage_key, ts, value, quality) VALUES (%s, %s, %s, %s, %s)", batch)
                total += len(batch)
    return total


def incremental_plane_sample_rows(*, series_by_id: dict[int, object], latest_by_series: dict[int, object], batch_size: int):
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
            cursor.execute(f"SELECT series_id, max(ts) FROM {QUESTDB_PLANE_SAMPLE_TABLE} WHERE series_id IN ({placeholders}) GROUP BY series_id", series_ids)
            return {int(series_id): questdb_utc(latest) for series_id, latest in cursor.fetchall() if latest is not None}


def questdb_trace_payload_json(
    *,
    profile_id: int,
    window_minutes: int,
    step_minutes: int = 1,
    set_index: int | None = None,
    set_label: str | None = None,
    well_id: str | None = None,
) -> bytes | None:
    metadata = questdb_profile_metadata(profile_id)
    if metadata is None:
        return None
    signals = metadata["signals"]
    with _request_gate:
        try:
            arrays = questdb_payload_arrays(signals, window_minutes=window_minutes, step_minutes=step_minutes)
        except psycopg.Error:
            reset_questdb_thread_connection()
            try:
                arrays = questdb_payload_arrays(signals, window_minutes=window_minutes, step_minutes=step_minutes)
            except psycopg.Error:
                arrays = None
    if arrays is None:
        return None
    end, x_values, y_values_by_signal = arrays
    payload = {
        "traceChart": {
            "x": x_values,
            "series": [questdb_series_payload(signal, y_values_by_signal[signal["id"]]) for signal in signals],
            "axisGroups": metadata["axis_groups"],
            "latestReadAt": (end - timedelta(minutes=1)).isoformat(),
            "windowDays": window_minutes / 1440,
            "windowMinutes": window_minutes,
            "stepMinutes": step_minutes,
            "windowLabel": "%s day%s" % (window_minutes // 1440, "" if window_minutes == 1440 else "s") if window_minutes % 1440 == 0 else "%s min" % window_minutes,
            "source": "questdb-plane-samples",
            "profileKey": metadata["profile_key"],
            "profileLabel": metadata["profile_label"],
            "setIndex": set_index,
            "setLabel": set_label,
            "wellId": well_id,
        },
        "traceError": "",
    }
    return orjson.dumps(payload)


def questdb_payload_arrays(signals: list[dict], *, window_minutes: int, step_minutes: int):
    connection = questdb_thread_connection()
    series_ids = sorted({signal["series_id"] for signal in signals if signal["series_id"] is not None})
    latest = questdb_latest_timestamp(series_ids, connection=connection)
    if latest is None:
        return None
    end = latest.replace(second=0, microsecond=0) + timedelta(minutes=1)
    start = end - timedelta(minutes=window_minutes)
    start_epoch = int(start.timestamp())
    point_count = window_minutes // step_minutes
    x_values = [start_epoch + index * step_minutes * 60 for index in range(point_count)]
    y_values_by_signal = {signal["id"]: [None] * point_count for signal in signals}
    signal_ids_by_series_id = signal_ids_by_series(signals)
    rows = questdb_rows(series_ids=series_ids, start=start, end=end, step_minutes=step_minutes, start_epoch=start_epoch, connection=connection)
    for series_id, timestamp, value in rows:
        epoch = int(timestamp.timestamp())
        offset_seconds = epoch - start_epoch
        if offset_seconds < 0 or offset_seconds % (step_minutes * 60) != 0:
            continue
        index = offset_seconds // (step_minutes * 60)
        if 0 <= index < point_count:
            for signal_id in signal_ids_by_series_id.get(series_id, []):
                y_values_by_signal[signal_id][index] = value
    return end, x_values, y_values_by_signal


def questdb_profile_metadata(profile_id: int) -> dict | None:
    now = time.monotonic()
    with _profile_cache_lock:
        cached = _profile_cache.get(profile_id)
        if cached and now - cached[0] <= _PROFILE_CACHE_SECONDS:
            return cached[1]
    profile = TraceProfile.objects.filter(id=profile_id).first()
    if profile is None:
        return None
    signal_rows = []
    for signal in profile.signals.select_related("tag", "series", "series__base_tag").filter(default_visible=True).order_by("sort_order", "id"):
        signal_rows.append(
            {
                "id": signal.id,
                "tag_id": signal.tag_id,
                "series_id": signal.series_id,
                "storage_key": signal.series_storage_key,
                "name": signal.display_label,
                "full_path": signal.chart_full_path,
                "unit": signal.display_unit,
                "axis_key": signal.axis_key,
                "axis_label": signal.axis_label or signal.axis_key.replace("-", " ").title(),
                "axis_unit": signal.axis_unit or signal.display_unit,
                "range": [signal.range_min, signal.range_max] if signal.range_min is not None and signal.range_max is not None else None,
                "sort_order": signal.sort_order,
            }
        )
    if not signal_rows:
        return None
    metadata = {
        "profile_key": profile.key,
        "profile_label": profile.label,
        "signals": signal_rows,
        "axis_groups": axis_groups(signal_rows),
    }
    with _profile_cache_lock:
        _profile_cache[profile_id] = (now, metadata)
    return metadata


def signal_ids_by_series(signals: list[dict]) -> dict[int, list[int]]:
    grouped: dict[int, list[int]] = {}
    for signal in signals:
        series_id = signal["series_id"]
        if series_id is None:
            continue
        grouped.setdefault(series_id, []).append(signal["id"])
    return grouped


def questdb_latest_timestamp(series_ids: list[int], connection=None):
    cache_key = tuple(sorted(series_ids))
    now = time.monotonic()
    with _latest_cache_lock:
        cached = _latest_cache.get(cache_key)
        if cached and now - cached[0] <= _LATEST_CACHE_SECONDS:
            return cached[1]
    if not series_ids:
        return None
    placeholders = ",".join(["%s"] * len(series_ids))
    with questdb_cursor(connection) as cursor:
        cursor.execute(f"SELECT max(ts) FROM {QUESTDB_PLANE_SAMPLE_TABLE} WHERE series_id IN ({placeholders})", series_ids)
        row = cursor.fetchone()
    latest = questdb_utc(row[0]) if row and row[0] is not None else None
    if latest is not None:
        with _latest_cache_lock:
            _latest_cache[cache_key] = (now, latest)
    return latest


def questdb_rows(*, series_ids: list[int], start, end, step_minutes: int = 1, start_epoch: int | None = None, connection=None) -> list[tuple[int, object, float]]:
    if not series_ids:
        return []
    placeholders = ",".join(["%s"] * len(series_ids))
    step_filter = ""
    params = [*series_ids, start, end]
    if step_minutes > 1 and start_epoch is not None:
        step_filter = " AND (extract(epoch from ts) - %s) %% %s = 0"
        params.extend([start_epoch, step_minutes * 60])
    with questdb_cursor(connection) as cursor:
        cursor.execute(
            f"SELECT series_id, ts, value FROM {QUESTDB_PLANE_SAMPLE_TABLE} WHERE series_id IN ({placeholders}) AND ts >= %s AND ts < %s{step_filter} ORDER BY series_id, ts",
            params,
        )
        return [(int(series_id), questdb_utc(timestamp), float(value)) for series_id, timestamp, value in cursor.fetchall()]


def questdb_utc(timestamp):
    if timestamp is None:
        return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=datetime_timezone.utc)
    return timestamp.astimezone(datetime_timezone.utc)


def questdb_series_payload(signal: dict, y_values: list[float | None]) -> dict:
    return {
        "rawCount": len(y_values),
        "tagId": signal["tag_id"],
        "seriesId": signal["series_id"],
        "storageKey": signal["storage_key"],
        "signalId": signal["id"],
        "name": signal["name"],
        "fullPath": signal["full_path"],
        "unit": signal["unit"],
        "axisKey": signal["axis_key"],
        "x": [],
        "y": y_values,
    }


def axis_groups(signals: list[dict]) -> list[dict]:
    groups = {}
    for index, signal in enumerate(signals, start=1):
        groups.setdefault(
            signal["axis_key"],
            {
                "key": signal["axis_key"],
                "label": signal["axis_label"],
                "unit": signal["axis_unit"],
                "range": signal["range"],
                "side": 1 if index == 1 else 3,
            },
        )
    return list(groups.values())
