from __future__ import annotations

from django.db import connection

from flux.trace.models import TraceCachePoint, TraceSignal


def postgres_trace_payload_json(
    *,
    profile_id: int,
    window_minutes: int,
    step_minutes: int = 1,
    set_index: int | None = None,
    set_label: str | None = None,
    well_id: str | None = None,
) -> bytes | None:
    if connection.vendor != "postgresql":
        return None
    profile_table = connection.ops.quote_name("trace_traceprofile")
    signal_table = connection.ops.quote_name("trace_tracesignal")
    point_table = connection.ops.quote_name(TraceCachePoint._meta.db_table)
    tag_table = connection.ops.quote_name("runtime_runtimetag")
    sql = f"""
        WITH visible_signals AS (
            SELECT
                s.id,
                s.tag_id,
                COALESCE(NULLIF(s.label, ''), t.display_name) AS name,
                '[' || t.provider || ']' || t.path AS full_path,
                COALESCE(NULLIF(s.unit, ''), t.engineering_units) AS unit,
                s.axis_key,
                COALESCE(NULLIF(s.axis_label, ''), initcap(replace(s.axis_key, '-', ' '))) AS axis_label,
                COALESCE(NULLIF(s.axis_unit, ''), COALESCE(NULLIF(s.unit, ''), t.engineering_units)) AS axis_unit,
                s.range_min,
                s.range_max,
                s.sort_order
            FROM {signal_table} s
            JOIN {tag_table} t ON t.id = s.tag_id
            WHERE s.profile_id = %s AND s.default_visible = true
        ),
        latest AS (
            SELECT max(p.timestamp) AS latest_timestamp
            FROM {point_table} p
            JOIN visible_signals s ON s.id = p.signal_id
        ),
        bounds AS (
            SELECT
                date_trunc('minute', COALESCE((SELECT latest_timestamp FROM latest), now())) + interval '1 minute' AS end_ts
        ),
        time_window AS (
            SELECT
                end_ts - (%s::int * interval '1 minute') AS start_ts,
                end_ts
            FROM bounds
        ),
        raw_points AS (
            SELECT
                s.id AS signal_id,
                p.timestamp,
                p.value_float,
                CASE
                    WHEN %s::int > 1
                    THEN floor((EXTRACT(EPOCH FROM p.timestamp) - EXTRACT(EPOCH FROM time_window.start_ts)) / (%s::int * 60))::bigint
                    ELSE EXTRACT(EPOCH FROM p.timestamp)::bigint
                END AS bucket
            FROM visible_signals s
            CROSS JOIN time_window
            JOIN {point_table} p ON p.signal_id = s.id
            WHERE p.timestamp >= time_window.start_ts AND p.timestamp < time_window.end_ts
        ),
        bucketed_points AS (
            SELECT DISTINCT ON (signal_id, bucket)
                signal_id,
                timestamp,
                value_float
            FROM raw_points
            ORDER BY signal_id, bucket, timestamp DESC
        ),
        x_values AS (
            SELECT epoch
            FROM (
                SELECT DISTINCT EXTRACT(EPOCH FROM timestamp)::bigint AS epoch
                FROM bucketed_points
            ) values_by_epoch
            ORDER BY epoch
        ),
        x_payload AS (
            SELECT COALESCE(jsonb_agg(epoch ORDER BY epoch), '[]'::jsonb) AS x_values
            FROM x_values
        ),
        series_payload AS (
            SELECT
                s.id,
                s.sort_order,
                jsonb_build_object(
                    'rawCount', COUNT(bp.value_float)::int,
                    'tagId', s.tag_id,
                    'signalId', s.id,
                    'name', s.name,
                    'fullPath', s.full_path,
                    'unit', s.unit,
                    'axisKey', s.axis_key,
                    'x', '[]'::jsonb,
                    'y', COALESCE(jsonb_agg(bp.value_float ORDER BY xv.epoch) FILTER (WHERE xv.epoch IS NOT NULL), '[]'::jsonb)
                ) AS series_json
            FROM visible_signals s
            LEFT JOIN x_values xv ON true
            LEFT JOIN bucketed_points bp ON bp.signal_id = s.id AND EXTRACT(EPOCH FROM bp.timestamp)::bigint = xv.epoch
            GROUP BY s.id, s.tag_id, s.name, s.full_path, s.unit, s.axis_key, s.sort_order
        ),
        axis_payload AS (
            SELECT jsonb_agg(axis_json ORDER BY first_sort) AS axis_groups
            FROM (
                SELECT DISTINCT ON (s.axis_key)
                    s.axis_key,
                    s.sort_order AS first_sort,
                    jsonb_build_object(
                        'key', s.axis_key,
                        'label', s.axis_label,
                        'unit', s.axis_unit,
                        'range', CASE WHEN s.range_min IS NULL OR s.range_max IS NULL THEN NULL ELSE jsonb_build_array(s.range_min, s.range_max) END,
                        'side', CASE WHEN s.sort_order = (SELECT min(sort_order) FROM visible_signals) THEN 1 ELSE 3 END
                    ) AS axis_json
                FROM visible_signals s
                ORDER BY s.axis_key, s.sort_order
            ) grouped_axes
        )
        SELECT jsonb_build_object(
            'traceChart', jsonb_build_object(
                'x', COALESCE((SELECT x_values FROM x_payload), '[]'::jsonb),
                'series', COALESCE((SELECT jsonb_agg(series_json ORDER BY sort_order, id) FROM series_payload), '[]'::jsonb),
                'axisGroups', COALESCE((SELECT axis_groups FROM axis_payload), '[]'::jsonb),
                'latestReadAt', (SELECT (end_ts - interval '1 minute')::text FROM time_window),
                'windowDays', (%s::float / 1440.0),
                'windowMinutes', %s::int,
                'stepMinutes', %s::int,
                'windowLabel', CASE WHEN %s::int %% 1440 = 0 THEN (%s::int / 1440)::text || CASE WHEN %s::int = 1440 THEN ' day' ELSE ' days' END ELSE %s::text || ' min' END,
                'source', 'trace-cache',
                'profileKey', p.key,
                'profileLabel', p.label,
                'setIndex', %s,
                'setLabel', %s,
                'wellId', %s
            ),
            'traceError', ''
        )::text
        FROM {profile_table} p
        WHERE p.id = %s
    """
    params = [
        profile_id,
        window_minutes,
        step_minutes,
        step_minutes,
        window_minutes,
        window_minutes,
        step_minutes,
        window_minutes,
        window_minutes,
        window_minutes,
        window_minutes,
        set_index,
        set_label,
        well_id,
        profile_id,
    ]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    if not row or row[0] is None:
        return None
    return row[0].encode()


def dense_y_values_by_signal(*, signals: list[TraceSignal], start, end, start_epoch: int, point_count: int, step_minutes: int = 1) -> dict[int, list[float | None]]:
    y_values_by_signal: dict[int, list[float | None]] = {signal.id: [None] * point_count for signal in signals}
    if not signals:
        return y_values_by_signal
    step_seconds = step_minutes * 60
    for signal_id, epoch_seconds, value in cache_point_epoch_rows(signals=signals, start=start, end=end):
        offset_seconds = epoch_seconds - start_epoch
        if offset_seconds < 0 or offset_seconds % step_seconds != 0:
            continue
        index = offset_seconds // step_seconds
        if 0 <= index < point_count:
            y_values_by_signal[signal_id][index] = value
    return y_values_by_signal


def cache_point_epoch_rows(*, signals: list[TraceSignal], start, end) -> list[tuple[int, int, float]]:
    if connection.vendor == "postgresql":
        return postgres_cache_point_epoch_rows(signals=signals, start=start, end=end)
    return orm_cache_point_epoch_rows(signals=signals, start=start, end=end)


def postgres_cache_point_epoch_rows(*, signals: list[TraceSignal], start, end) -> list[tuple[int, int, float]]:
    signal_ids = [signal.id for signal in signals]
    table = connection.ops.quote_name(TraceCachePoint._meta.db_table)
    timestamp_column = connection.ops.quote_name("timestamp")
    signal_column = connection.ops.quote_name("signal_id")
    value_column = connection.ops.quote_name("value_float")
    sql = f"""
        SELECT {signal_column}, EXTRACT(EPOCH FROM {timestamp_column})::bigint AS epoch_seconds, {value_column}
        FROM {table}
        WHERE {signal_column} = ANY(%s) AND {timestamp_column} >= %s AND {timestamp_column} < %s
        ORDER BY {signal_column}, {timestamp_column}
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [[*signal_ids], start, end])
        return [(int(signal_id), int(epoch_seconds), float(value)) for signal_id, epoch_seconds, value in cursor.fetchall()]


def orm_cache_point_epoch_rows(*, signals: list[TraceSignal], start, end) -> list[tuple[int, int, float]]:
    return [
        (signal_id, int(timestamp.timestamp()), value)
        for signal_id, timestamp, value in TraceCachePoint.objects.filter(
            signal__in=signals,
            timestamp__gte=start,
            timestamp__lt=end,
        ).values_list("signal_id", "timestamp", "value_float")
    ]
