import uuid

from django.db import migrations, models
import django.db.models.deletion


def _device_namespace_from_sim(sim_device):
    return "provider:%s" % sim_device.provider.name


def _device_namespace_from_field(field_device, sim_devices_by_id):
    metadata = field_device.config or {}
    sim_device_id = metadata.get("sim_device_id") if metadata.get("source") == "sim_device" else None
    sim_device = sim_devices_by_id.get(sim_device_id)
    if sim_device is not None:
        return _device_namespace_from_sim(sim_device), sim_device.name
    endpoint_name = field_device.endpoint.name if field_device.endpoint_id else "unknown"
    return "endpoint:%s" % endpoint_name, field_device.name


def _tag_full_path(provider, tagpath):
    return "[%s]%s" % (provider, tagpath) if tagpath else "[%s]" % provider


def _safe_update(instance, **values):
    changed = False
    for field, value in values.items():
        if value in (None, "") and getattr(instance, field) not in (None, ""):
            continue
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            changed = True
    if changed:
        instance.save()


def _get_or_create_device(Device, *, namespace, name, defaults):
    device, created = Device.objects.get_or_create(namespace=namespace, name=name, defaults=defaults)
    if not created:
        _safe_update(device, **defaults)
    return device


def _get_or_create_tag(Tag, *, provider, tagpath, defaults):
    defaults.setdefault("full_path", _tag_full_path(provider, tagpath))
    tag, created = Tag.objects.get_or_create(provider=provider, tagpath=tagpath, defaults=defaults)
    if not created:
        _safe_update(tag, **defaults)
    return tag


def _flush_tags(Tag, pending):
    if not pending:
        return
    Tag.objects.bulk_create(pending, ignore_conflicts=True, batch_size=5000)
    pending.clear()


def backfill_kernel_device_tag(apps, schema_editor):
    Device = apps.get_model("base", "Device")
    Tag = apps.get_model("base", "Tag")
    SimDevice = apps.get_model("base", "SimDevice")
    SimDeviceTag = apps.get_model("base", "SimDeviceTag")
    FieldDevice = apps.get_model("base", "FieldDevice")
    FieldTag = apps.get_model("base", "FieldTag")

    sim_devices = list(SimDevice.objects.select_related("provider", "driver"))
    sim_devices_by_id = {device.id: device for device in sim_devices}
    field_tags = list(FieldTag.objects.select_related("device", "device__endpoint"))
    linked_sim_tag_ids = set()
    for field_tag in field_tags:
        metadata = field_tag.config or {}
        if metadata.get("source") == "sim_device_tag" and metadata.get("sim_device_tag_id"):
            linked_sim_tag_ids.add(metadata["sim_device_tag_id"])
    sim_tags_by_id = {
        tag.id: tag
        for tag in SimDeviceTag.objects.filter(id__in=linked_sim_tag_ids).select_related(
            "provider", "device", "device__provider", "device__driver", "tag_node"
        )
    }

    for sim_device in sim_devices:
        _get_or_create_device(
            Device,
            namespace=_device_namespace_from_sim(sim_device),
            name=sim_device.name,
            defaults={
                "device_type": sim_device.driver.label if sim_device.driver_id else "generic",
                "enabled": sim_device.enabled,
                "description": sim_device.source_detail or "",
            },
        )

    for field_device in FieldDevice.objects.select_related("endpoint"):
        namespace, name = _device_namespace_from_field(field_device, sim_devices_by_id)
        _get_or_create_device(
            Device,
            namespace=namespace,
            name=name,
            defaults={
                "device_type": field_device.device_type or "generic",
                "enabled": field_device.enabled,
                "description": field_device.description or "",
            },
        )

    devices_by_key = {(device.namespace, device.name): device for device in Device.objects.all()}
    pending_tags = []
    for sim_tag in SimDeviceTag.objects.select_related(
        "provider", "device", "device__provider", "device__driver"
    ).iterator(chunk_size=5000):
        base_device = devices_by_key[(_device_namespace_from_sim(sim_tag.device), sim_tag.device.name)]
        update_rate_ms = (sim_tag.device.config or {}).get("update_rate_ms", 1000)
        if not isinstance(update_rate_ms, int) or update_rate_ms <= 0:
            update_rate_ms = 1000
        provider = sim_tag.provider.name
        tagpath = sim_tag.source_path or "%s/%s" % (sim_tag.device.name, sim_tag.tag_name)
        pending_tags.append(
            Tag(
                device_id=base_device.id,
                provider=provider,
                tagpath=tagpath,
                full_path=_tag_full_path(provider, tagpath),
                name=sim_tag.tag_name or tagpath.rsplit("/", 1)[-1],
                data_type=sim_tag.data_type or "",
                update_rate_ms=update_rate_ms,
                enabled=sim_tag.enabled,
                description=sim_tag.source_path or "",
            )
        )
        if len(pending_tags) >= 5000:
            _flush_tags(Tag, pending_tags)
    _flush_tags(Tag, pending_tags)

    for field_tag in field_tags:
        base_device = None
        if field_tag.device_id:
            namespace, name = _device_namespace_from_field(field_tag.device, sim_devices_by_id)
            base_device = _get_or_create_device(
                Device,
                namespace=namespace,
                name=name,
                defaults={
                    "device_type": field_tag.device.device_type or "generic",
                    "enabled": field_tag.device.enabled,
                    "description": field_tag.device.description or "",
                },
            )
        metadata = field_tag.config or {}
        sim_tag_id = metadata.get("sim_device_tag_id") if metadata.get("source") == "sim_device_tag" else None
        sim_tag = sim_tags_by_id.get(sim_tag_id)
        if sim_tag is not None:
            provider = sim_tag.provider.name
            tagpath = sim_tag.source_path or "%s/%s" % (sim_tag.device.name, sim_tag.tag_name)
            tag_name = sim_tag.tag_name or field_tag.name
        else:
            provider = field_tag.device.endpoint.name if field_tag.device.endpoint_id else field_tag.device.browse_path
            tagpath = "%s/%s" % (field_tag.device.name, field_tag.name)
            tag_name = field_tag.name
        _get_or_create_tag(
            Tag,
            provider=provider,
            tagpath=tagpath,
            defaults={
                "device": base_device,
                "name": tag_name,
                "data_type": field_tag.data_type or "",
                "update_rate_ms": field_tag.update_rate_ms or 1000,
                "enabled": field_tag.enabled,
                "description": field_tag.description or "",
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0009_drop_fieldnode"),
    ]

    operations = [
        migrations.RunSQL(sql="CREATE SCHEMA IF NOT EXISTS base;", reverse_sql=migrations.RunSQL.noop),
        migrations.CreateModel(
            name="Device",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("guid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("namespace", models.CharField(default="default", max_length=255)),
                ("name", models.CharField(max_length=120)),
                ("device_type", models.CharField(default="generic", max_length=120)),
                ("enabled", models.BooleanField(default=True)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": '"base"."device"',
                "ordering": ["namespace", "name"],
            },
        ),
        migrations.CreateModel(
            name="Tag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("guid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("provider", models.CharField(default="default", max_length=120)),
                ("tagpath", models.CharField(max_length=1200)),
                ("full_path", models.CharField(max_length=1400)),
                ("name", models.CharField(max_length=255)),
                ("data_type", models.CharField(blank=True, max_length=80)),
                ("update_rate_ms", models.PositiveIntegerField(default=1000)),
                ("enabled", models.BooleanField(default=True)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("device", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tags", to="base.device")),
            ],
            options={
                "db_table": '"base"."tag"',
                "ordering": ["provider", "tagpath"],
            },
        ),
        migrations.AddConstraint(
            model_name="device",
            constraint=models.UniqueConstraint(fields=("namespace", "name"), name="unique_base_device_namespace_name"),
        ),
        migrations.AddIndex(
            model_name="device",
            index=models.Index(fields=["namespace", "name"], name="base_device_namespace_name_idx"),
        ),
        migrations.AddIndex(
            model_name="device",
            index=models.Index(fields=["device_type"], name="base_device_type_idx"),
        ),
        migrations.AddIndex(
            model_name="device",
            index=models.Index(fields=["enabled"], name="base_device_enabled_idx"),
        ),
        migrations.AddConstraint(
            model_name="tag",
            constraint=models.UniqueConstraint(fields=("provider", "tagpath"), name="unique_base_tag_provider_path"),
        ),
        migrations.AddIndex(
            model_name="tag",
            index=models.Index(fields=["device", "name"], name="base_tag_device_name_idx"),
        ),
        migrations.AddIndex(
            model_name="tag",
            index=models.Index(fields=["provider", "name"], name="base_tag_provider_name_idx"),
        ),
        migrations.AddIndex(
            model_name="tag",
            index=models.Index(fields=["enabled"], name="base_tag_enabled_idx"),
        ),
        migrations.RunPython(backfill_kernel_device_tag, migrations.RunPython.noop),
    ]
