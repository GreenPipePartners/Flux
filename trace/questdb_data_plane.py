from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from datetime import timedelta, timezone as datetime_timezone

import orjson
import psycopg

from flux.trace.models import TraceCachePoint, TraceProfile, TraceSignal


QUESTDB_DSN = os.getenv("QUESTDB_DSN", "postgresql://admin:quest@localhost:8812/qdb")
_thread_local = threading.local()
_latest_cache: dict[tuple[int, ...], tuple[float, object]] = {}
_latest_cache_lock = threading.Lock()
_profile_cache: dict[int, tuple[float, dict]] = {}
_profile_cache_lock = threading.Lock()
_LATEST_CACHE_SECONDS = float(os.getenv("QUESTDB_LATEST_CACHE_SECONDS", "30"))
_PROFILE_CACHE_SECONDS = float(os.getenv("QUESTDB_PROFILE_CACHE_SECONDS", "60"))
_request_gate = threading.BoundedSemaphore(int(os.getenv("QUESTDB_TRACE_CONCURRENCY", "8")))


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
                cursor.execute("DROP TABLE IF EXISTS trace_points")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trace_points (
                    signal_id LONG,
                    signal_key SYMBOL INDEX,
                    ts TIMESTAMP,
                    value DOUBLE,
                    quality SYMBOL
                ) timestamp(ts) PARTITION BY DAY WAL
                """
            )


def export_trace_cache_to_questdb(*, profile_keys: list[str], replace: bool = False, batch_size: int = 5000) -> int:
    ensure_questdb_schema(replace=replace)
    signals = list(TraceSignal.objects.filter(profile__key__in=profile_keys).order_by("id"))
    latest_by_signal = {} if replace else questdb_latest_timestamps_by_signal([signal.id for signal in signals])
    total = 0
    rows = incremental_trace_cache_rows(signals=signals, latest_by_signal=latest_by_signal, batch_size=batch_size)
    with questdb_connect() as connection:
        with connection.cursor() as cursor:
            batch = []
            for signal_id, timestamp, value, quality in rows:
                    batch.append((signal_id, str(signal_id), timestamp, value, quality or "Good"))
                    if len(batch) >= batch_size:
                        cursor.executemany("INSERT INTO trace_points (signal_id, signal_key, ts, value, quality) VALUES (%s, %s, %s, %s, %s)", batch)
                    total += len(batch)
                    batch = []
            if batch:
                cursor.executemany("INSERT INTO trace_points (signal_id, signal_key, ts, value, quality) VALUES (%s, %s, %s, %s, %s)", batch)
                total += len(batch)
    return total


def incremental_trace_cache_rows(*, signals: list[TraceSignal], latest_by_signal: dict[int, object], batch_size: int):
    for signal in signals:
        queryset = TraceCachePoint.objects.filter(signal=signal).order_by("timestamp")
        latest = latest_by_signal.get(signal.id)
        if latest is not None:
            queryset = queryset.filter(timestamp__gt=latest)
        yield from queryset.values_list("signal_id", "timestamp", "value_float", "quality_code").iterator(chunk_size=batch_size)


def questdb_latest_timestamps_by_signal(signal_ids: list[int]) -> dict[int, object]:
    if not signal_ids:
        return {}
    signal_keys = [str(signal_id) for signal_id in signal_ids]
    placeholders = ",".join(["%s"] * len(signal_keys))
    with questdb_connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT signal_id, max(ts) FROM trace_points WHERE signal_key IN ({placeholders}) GROUP BY signal_id", signal_keys)
            return {int(signal_id): questdb_utc(latest) for signal_id, latest in cursor.fetchall() if latest is not None}


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
            "source": "questdb-trace-cache",
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
    signal_ids = [signal["id"] for signal in signals]
    latest = questdb_latest_timestamp(signal_ids, connection=connection)
    if latest is None:
        return None
    end = latest.replace(second=0, microsecond=0) + timedelta(minutes=1)
    start = end - timedelta(minutes=window_minutes)
    start_epoch = int(start.timestamp())
    point_count = window_minutes // step_minutes
    x_values = [start_epoch + index * step_minutes * 60 for index in range(point_count)]
    y_values_by_signal = {signal["id"]: [None] * point_count for signal in signals}
    rows = questdb_rows(signal_ids=signal_ids, start=start, end=end, step_minutes=step_minutes, start_epoch=start_epoch, connection=connection)
    for signal_id, timestamp, value in rows:
        epoch = int(timestamp.timestamp())
        offset_seconds = epoch - start_epoch
        if offset_seconds < 0 or offset_seconds % (step_minutes * 60) != 0:
            continue
        index = offset_seconds // (step_minutes * 60)
        if 0 <= index < point_count:
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
    for signal in profile.signals.select_related("tag").filter(default_visible=True).order_by("sort_order", "id"):
        signal_rows.append(
            {
                "id": signal.id,
                "tag_id": signal.tag_id,
                "name": signal.display_label,
                "full_path": signal.tag.full_path,
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


def questdb_latest_timestamp(signal_ids: list[int], connection=None):
    cache_key = tuple(sorted(signal_ids))
    now = time.monotonic()
    with _latest_cache_lock:
        cached = _latest_cache.get(cache_key)
        if cached and now - cached[0] <= _LATEST_CACHE_SECONDS:
            return cached[1]
    signal_keys = [str(signal_id) for signal_id in signal_ids]
    placeholders = ",".join(["%s"] * len(signal_keys))
    with questdb_cursor(connection) as cursor:
        cursor.execute(f"SELECT max(ts) FROM trace_points WHERE signal_key IN ({placeholders})", signal_keys)
        row = cursor.fetchone()
    latest = questdb_utc(row[0]) if row and row[0] is not None else None
    if latest is not None:
        with _latest_cache_lock:
            _latest_cache[cache_key] = (now, latest)
    return latest


def questdb_rows(*, signal_ids: list[int], start, end, step_minutes: int = 1, start_epoch: int | None = None, connection=None) -> list[tuple[int, object, float]]:
    signal_keys = [str(signal_id) for signal_id in signal_ids]
    placeholders = ",".join(["%s"] * len(signal_keys))
    step_filter = ""
    params = [*signal_keys, start, end]
    if step_minutes > 1 and start_epoch is not None:
        step_filter = " AND (extract(epoch from ts) - %s) %% %s = 0"
        params.extend([start_epoch, step_minutes * 60])
    with questdb_cursor(connection) as cursor:
        cursor.execute(
            f"SELECT signal_id, ts, value FROM trace_points WHERE signal_key IN ({placeholders}) AND ts >= %s AND ts < %s{step_filter} ORDER BY signal_id, ts",
            params,
        )
        return [(int(signal_id), questdb_utc(timestamp), float(value)) for signal_id, timestamp, value in cursor.fetchall()]


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
