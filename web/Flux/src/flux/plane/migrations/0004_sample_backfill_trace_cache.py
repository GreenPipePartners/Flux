from django.db import migrations, models
import django.db.models.deletion


BATCH_SIZE = 5000


def backfill_trace_cache_points(apps, schema_editor):
    TraceCachePoint = apps.get_model("trace", "TraceCachePoint")
    TraceSignal = apps.get_model("trace", "TraceSignal")
    Series = apps.get_model("plane", "Series")
    Sample = apps.get_model("plane", "Sample")

    pending = []
    for point in TraceCachePoint.objects.select_related("signal", "signal__tag").only(
        "timestamp",
        "value_float",
        "quality_code",
        "signal_id",
        "signal__series_id",
        "signal__tag__provider",
        "signal__tag__path",
    ).iterator(chunk_size=BATCH_SIZE):
        pending.append(point)
        if len(pending) >= BATCH_SIZE:
            flush_point_batch(TraceSignal, Series, Sample, pending)
            pending = []
    if pending:
        flush_point_batch(TraceSignal, Series, Sample, pending)


def flush_point_batch(TraceSignal, Series, Sample, points):
    full_paths = {runtime_full_path(point.signal.tag) for point in points if point.signal_id and point.signal.tag_id}
    series_by_path = {
        series.base_tag.full_path: series
        for series in Series.objects.select_related("base_tag").filter(base_tag__full_path__in=full_paths).only("id", "base_tag__full_path")
    }
    signal_updates = {}
    rows_by_key = {}
    for point in points:
        if not point.signal_id:
            continue
        series_id = point.signal.series_id
        if series_id is None:
            series = series_by_path.get(runtime_full_path(point.signal.tag))
            if series is None:
                continue
            series_id = series.id
            point.signal.series_id = series_id
            signal_updates[point.signal_id] = point.signal
        rows_by_key[(series_id, point.timestamp)] = Sample(
            series_id=series_id,
            timestamp=point.timestamp,
            value_float=point.value_float,
            quality_code=point.quality_code,
        )
    if signal_updates:
        TraceSignal.objects.bulk_update(signal_updates.values(), ["series"], batch_size=BATCH_SIZE)
    rows = list(rows_by_key.values())
    if rows:
        Sample.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["series", "timestamp"],
            update_fields=["value_float", "quality_code", "updated_at"],
            batch_size=BATCH_SIZE,
        )


def runtime_full_path(tag) -> str:
    return "[%s]%s" % (tag.provider, tag.path)


class Migration(migrations.Migration):

    dependencies = [
        ("plane", "0003_backfill_runtime_snapshots"),
        ("trace", "0003_signal_series"),
    ]

    operations = [
        migrations.CreateModel(
            name="Sample",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField()),
                ("value_float", models.FloatField()),
                ("quality_code", models.CharField(default="Good", max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("series", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="samples", to="plane.series")),
            ],
            options={
                "db_table": '"plane"."sample"',
                "ordering": ["-timestamp"],
            },
        ),
        migrations.AddIndex(
            model_name="sample",
            index=models.Index(fields=["series", "-timestamp"], name="plane_sample_series_time_idx"),
        ),
        migrations.AddIndex(
            model_name="sample",
            index=models.Index(fields=["timestamp"], name="plane_sample_time_idx"),
        ),
        migrations.AddConstraint(
            model_name="sample",
            constraint=models.UniqueConstraint(fields=("series", "timestamp"), name="unique_plane_sample_series_timestamp"),
        ),
        migrations.RunPython(backfill_trace_cache_points, migrations.RunPython.noop),
    ]
