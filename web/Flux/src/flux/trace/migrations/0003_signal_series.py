from django.db import migrations, models
import django.db.models.deletion


BATCH_SIZE = 5000


def backfill_trace_signal_series(apps, schema_editor):
    Signal = apps.get_model("trace", "TraceSignal")
    Series = apps.get_model("plane", "Series")
    pending = []
    for signal in Signal.objects.select_related("tag").only(
        "id", "series_id", "tag__provider", "tag__path"
    ).iterator(chunk_size=BATCH_SIZE):
        if signal.series_id:
            continue
        pending.append(signal)
        if len(pending) >= BATCH_SIZE:
            flush_signal_batch(Signal, Series, pending)
            pending = []
    if pending:
        flush_signal_batch(Signal, Series, pending)


def flush_signal_batch(Signal, Series, signals):
    full_paths = {"[%s]%s" % (signal.tag.provider, signal.tag.path) for signal in signals if signal.tag_id}
    series_by_path = {
        series.base_tag.full_path: series
        for series in Series.objects.select_related("base_tag").filter(base_tag__full_path__in=full_paths).only("id", "base_tag__full_path")
    }
    updates = []
    for signal in signals:
        series = series_by_path.get("[%s]%s" % (signal.tag.provider, signal.tag.path))
        if series is None:
            continue
        signal.series_id = series.id
        updates.append(signal)
    if updates:
        Signal.objects.bulk_update(updates, ["series"], batch_size=BATCH_SIZE)


class Migration(migrations.Migration):

    dependencies = [
        ("plane", "0001_initial"),
        ("trace", "0002_trace_annotations"),
    ]

    operations = [
        migrations.AddField(
            model_name="tracesignal",
            name="series",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="chart_signals", to="plane.series"),
        ),
        migrations.RunPython(backfill_trace_signal_series, migrations.RunPython.noop),
    ]
