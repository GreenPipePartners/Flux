from django.db import migrations, models
import django.db.models.deletion


BATCH_SIZE = 5000


def backfill_spot_point_series(apps, schema_editor):
    Point = apps.get_model("live", "LiveCardPointDefinition")
    Series = apps.get_model("plane", "Series")
    pending = []
    for point in Point.objects.all().only("id", "full_path", "series_id").iterator(chunk_size=BATCH_SIZE):
        if point.series_id:
            continue
        pending.append(point)
        if len(pending) >= BATCH_SIZE:
            flush_point_batch(Point, Series, pending)
            pending = []
    if pending:
        flush_point_batch(Point, Series, pending)


def flush_point_batch(Point, Series, points):
    paths = {point.full_path for point in points if point.full_path}
    series_by_path = {
        series.base_tag.full_path: series
        for series in Series.objects.select_related("base_tag").filter(base_tag__full_path__in=paths).only("id", "base_tag__full_path")
    }
    updates = []
    for point in points:
        series = series_by_path.get(point.full_path)
        if series is None:
            continue
        point.series_id = series.id
        updates.append(point)
    if updates:
        Point.objects.bulk_update(updates, ["series"], batch_size=BATCH_SIZE)


class Migration(migrations.Migration):

    dependencies = [
        ("plane", "0001_initial"),
        ("live", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="livecardpointdefinition",
            name="series",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="spot_points", to="plane.series"),
        ),
        migrations.RunPython(backfill_spot_point_series, migrations.RunPython.noop),
    ]
