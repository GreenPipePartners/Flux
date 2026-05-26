import hashlib

from django.db import migrations, models
import django.db.models.deletion


BATCH_SIZE = 5000


def entity_key_hash(kind: str, natural_key: str) -> str:
    return hashlib.sha256(f"{kind}\0{natural_key}".encode("utf-8")).hexdigest()


def backfill_plane_series(apps, schema_editor):
    Entity = apps.get_model("base", "Entity")
    Tag = apps.get_model("base", "Tag")
    Series = apps.get_model("plane", "Series")
    pending = []
    for tag in Tag.objects.all().only("id", "full_path", "name", "enabled", "update_rate_ms").iterator(chunk_size=BATCH_SIZE):
        pending.append(tag)
        if len(pending) >= BATCH_SIZE:
            flush_series_batch(Entity, Series, pending)
            pending = []
    if pending:
        flush_series_batch(Entity, Series, pending)


def flush_series_batch(Entity, Series, tags):
    kind = "plane.series"
    entities = []
    hashes = []
    for tag in tags:
        key_hash = entity_key_hash(kind, tag.full_path)
        hashes.append(key_hash)
        entities.append(
            Entity(
                kind=kind,
                natural_key=tag.full_path,
                natural_key_hash=key_hash,
                display_name=(tag.name or tag.full_path.rsplit("/", 1)[-1])[:255],
            )
        )
    Entity.objects.bulk_create(entities, ignore_conflicts=True, batch_size=BATCH_SIZE)
    entities_by_hash = {
        entity.natural_key_hash: entity
        for entity in Entity.objects.filter(kind=kind, natural_key_hash__in=hashes).only("id", "natural_key_hash")
    }
    rows = []
    for tag in tags:
        rows.append(
            Series(
                entity_id=entities_by_hash[entity_key_hash(kind, tag.full_path)].id,
                base_tag_id=tag.id,
                enabled=tag.enabled,
                latest_enabled=True,
                history_enabled=True,
                sample_interval_ms=tag.update_rate_ms or 1000,
                storage_key=tag.full_path,
            )
        )
    Series.objects.bulk_create(rows, ignore_conflicts=True, batch_size=BATCH_SIZE)


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("base", "0012_entity"),
    ]

    operations = [
        migrations.RunSQL(sql="CREATE SCHEMA IF NOT EXISTS plane;", reverse_sql=migrations.RunSQL.noop),
        migrations.CreateModel(
            name="Series",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=True)),
                ("latest_enabled", models.BooleanField(default=True)),
                ("history_enabled", models.BooleanField(default=True)),
                ("sample_interval_ms", models.PositiveIntegerField(default=1000)),
                ("storage_key", models.CharField(max_length=1400)),
                ("retention_policy", models.CharField(default="default", max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("base_tag", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="plane_series", to="base.tag")),
                ("entity", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="plane_series", to="base.entity")),
            ],
            options={
                "db_table": '"plane"."series"',
                "ordering": ["base_tag__provider", "base_tag__tagpath"],
            },
        ),
        migrations.CreateModel(
            name="Latest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("value", models.JSONField(blank=True, null=True)),
                ("quality_code", models.CharField(default="Unknown", max_length=120)),
                ("value_timestamp", models.DateTimeField(blank=True, null=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("series", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="latest", to="plane.series")),
            ],
            options={
                "db_table": '"plane"."latest"',
                "ordering": ["series"],
            },
        ),
        migrations.CreateModel(
            name="WindowStat",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("window", models.CharField(choices=[("today", "Today"), ("rolling_7d", "Rolling 7 days"), ("rolling_30d", "Rolling 30 days")], max_length=40)),
                ("min_value", models.FloatField(blank=True, null=True)),
                ("max_value", models.FloatField(blank=True, null=True)),
                ("sample_count", models.PositiveIntegerField(default=0)),
                ("window_start", models.DateTimeField()),
                ("window_end", models.DateTimeField()),
                ("computed_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("series", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="window_stats", to="plane.series")),
            ],
            options={
                "db_table": '"plane"."window_stat"',
                "ordering": ["series", "window"],
            },
        ),
        migrations.AddIndex(
            model_name="series",
            index=models.Index(fields=["enabled"], name="plane_series_enabled_idx"),
        ),
        migrations.AddIndex(
            model_name="series",
            index=models.Index(fields=["latest_enabled"], name="plane_series_latest_idx"),
        ),
        migrations.AddIndex(
            model_name="series",
            index=models.Index(fields=["history_enabled"], name="plane_series_history_idx"),
        ),
        migrations.AddIndex(
            model_name="latest",
            index=models.Index(fields=["read_at"], name="plane_latest_read_idx"),
        ),
        migrations.AddConstraint(
            model_name="windowstat",
            constraint=models.UniqueConstraint(fields=("series", "window"), name="unique_plane_window_stat"),
        ),
        migrations.AddIndex(
            model_name="windowstat",
            index=models.Index(fields=["series", "window"], name="plane_window_series_idx"),
        ),
        migrations.AddIndex(
            model_name="windowstat",
            index=models.Index(fields=["computed_at"], name="plane_window_computed_idx"),
        ),
        migrations.RunPython(backfill_plane_series, migrations.RunPython.noop),
    ]
