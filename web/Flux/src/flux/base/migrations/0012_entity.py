import hashlib
import uuid

from django.db import migrations, models
import django.db.models.deletion


BATCH_SIZE = 5000


def entity_key_hash(kind: str, natural_key: str) -> str:
    return hashlib.sha256(f"{kind}\0{natural_key}".encode("utf-8")).hexdigest()


def backfill_entity_links(apps, schema_editor):
    Entity = apps.get_model("base", "Entity")
    Device = apps.get_model("base", "Device")
    Tag = apps.get_model("base", "Tag")
    backfill_model_entities(
        Entity,
        Device,
        kind="base.device",
        row_values=lambda row: (f"{row.namespace}:{row.name}", row.name),
        queryset=Device.objects.all().only("id", "namespace", "name", "entity_id"),
    )
    backfill_model_entities(
        Entity,
        Tag,
        kind="base.tag",
        row_values=lambda row: (row.full_path, row.name or row.full_path.rsplit("/", 1)[-1]),
        queryset=Tag.objects.all().only("id", "full_path", "name", "entity_id"),
    )


def backfill_model_entities(Entity, Model, *, kind, row_values, queryset):
    pending_rows = []
    for row in queryset.iterator(chunk_size=BATCH_SIZE):
        if row.entity_id:
            continue
        pending_rows.append(row)
        if len(pending_rows) >= BATCH_SIZE:
            flush_entity_batch(Entity, Model, kind=kind, row_values=row_values, rows=pending_rows)
            pending_rows = []
    if pending_rows:
        flush_entity_batch(Entity, Model, kind=kind, row_values=row_values, rows=pending_rows)


def flush_entity_batch(Entity, Model, *, kind, row_values, rows):
    keys = []
    entities = []
    for row in rows:
        natural_key, display_name = row_values(row)
        key_hash = entity_key_hash(kind, natural_key)
        keys.append(key_hash)
        entities.append(
            Entity(
                kind=kind,
                natural_key=natural_key,
                natural_key_hash=key_hash,
                display_name=display_name[:255],
            )
        )
    Entity.objects.bulk_create(entities, ignore_conflicts=True, batch_size=BATCH_SIZE)
    entities_by_hash = {
        entity.natural_key_hash: entity
        for entity in Entity.objects.filter(kind=kind, natural_key_hash__in=keys).only("id", "natural_key_hash")
    }
    updates = []
    for row in rows:
        natural_key, _display_name = row_values(row)
        row.entity_id = entities_by_hash[entity_key_hash(kind, natural_key)].id
        updates.append(row)
    Model.objects.bulk_update(updates, ["entity"], batch_size=BATCH_SIZE)


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0011_drop_legacy_device_tag_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="Entity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("guid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("kind", models.CharField(choices=[("base.tag", "Base tag"), ("base.device", "Base device"), ("plane.series", "Plane series"), ("bridge.connection", "Bridge connection"), ("serve.worker", "Serve worker"), ("field.endpoint", "Field endpoint"), ("sim.device", "Sim device")], max_length=80)),
                ("natural_key", models.TextField()),
                ("natural_key_hash", models.CharField(max_length=64)),
                ("display_name", models.CharField(max_length=255)),
                ("retired_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": '"base"."entity"',
                "ordering": ["kind", "natural_key"],
            },
        ),
        migrations.AddField(
            model_name="device",
            name="entity",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="device", to="base.entity"),
        ),
        migrations.AddField(
            model_name="tag",
            name="entity",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="tag", to="base.entity"),
        ),
        migrations.AddConstraint(
            model_name="entity",
            constraint=models.UniqueConstraint(fields=("kind", "natural_key_hash"), name="unique_base_entity_kind_key_hash"),
        ),
        migrations.AddIndex(
            model_name="entity",
            index=models.Index(fields=["kind", "display_name"], name="base_entity_kind_name_idx"),
        ),
        migrations.AddIndex(
            model_name="entity",
            index=models.Index(fields=["retired_at"], name="base_entity_retired_idx"),
        ),
        migrations.RunPython(backfill_entity_links, migrations.RunPython.noop),
    ]
