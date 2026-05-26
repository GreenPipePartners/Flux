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


def _field_device_mode(field_device):
    metadata = field_device.config or {}
    return metadata.get("mode") or "standard"


def _simulation_type_for_data_type(data_type):
    if data_type == "bool":
        return "toggle"
    if data_type == "string":
        return "static"
    return "ramp"


def _get_base_device(Device, *, namespace, name):
    return Device.objects.get(namespace=namespace, name=name)


def _get_base_tag(Tag, *, provider, tagpath):
    return Tag.objects.get(provider=provider, tagpath=tagpath)


def _sim_tag_identity_from_field(field_tag, sim_tags_by_id):
    metadata = field_tag.config or {}
    sim_tag_id = metadata.get("sim_device_tag_id") if metadata.get("source") == "sim_device_tag" else None
    sim_tag = sim_tags_by_id.get(sim_tag_id)
    if sim_tag is not None:
        return sim_tag.provider.name, sim_tag.source_path or "%s/%s" % (sim_tag.device.name, sim_tag.tag_name), sim_tag
    provider = field_tag.device.endpoint.name if field_tag.device.endpoint_id else field_tag.device.browse_path
    return provider, "%s/%s" % (field_tag.device.name, field_tag.name), None


def _upsert_device_config(DeviceConfig, *, base_device, defaults):
    config, created = DeviceConfig.objects.get_or_create(base_device=base_device, defaults=defaults)
    if created:
        return config
    changed = False
    for field, value in defaults.items():
        if value in (None, "") and getattr(config, field) not in (None, ""):
            continue
        if getattr(config, field) != value:
            setattr(config, field, value)
            changed = True
    if changed:
        config.save()
    return config


def _upsert_tag_config(TagConfig, *, sim_device, base_tag, defaults):
    config, created = TagConfig.objects.get_or_create(base_tag=base_tag, defaults={"sim_device": sim_device, **defaults})
    if created:
        return config
    changed = False
    if config.sim_device_id != sim_device.id:
        config.sim_device = sim_device
        changed = True
    for field, value in defaults.items():
        if value in (None, "") and getattr(config, field) not in (None, ""):
            continue
        if getattr(config, field) != value:
            setattr(config, field, value)
            changed = True
    if changed:
        config.save()
    return config


def _flush_sim_tag_configs(TagConfig, Tag, pending_sim_tags, sim_device_config_ids):
    if not pending_sim_tags:
        return
    providers = {tag.provider.name for tag in pending_sim_tags}
    tagpaths = {tag.source_path or "%s/%s" % (tag.device.name, tag.tag_name) for tag in pending_sim_tags}
    base_tags = {
        (tag.provider, tag.tagpath): tag
        for tag in Tag.objects.filter(provider__in=providers, tagpath__in=tagpaths).only("id", "provider", "tagpath")
    }
    configs = []
    for sim_tag in pending_sim_tags:
        provider = sim_tag.provider.name
        tagpath = sim_tag.source_path or "%s/%s" % (sim_tag.device.name, sim_tag.tag_name)
        base_tag = base_tags.get((provider, tagpath))
        sim_device_id = sim_device_config_ids.get(sim_tag.device_id)
        if base_tag is None or sim_device_id is None:
            continue
        configs.append(
            TagConfig(
                sim_device_id=sim_device_id,
                base_tag_id=base_tag.id,
                source_tag_node_id=sim_tag.tag_node_id,
                source_path=sim_tag.source_path or "",
                tag_name=sim_tag.tag_name or "",
                simulation_type=_simulation_type_for_data_type(sim_tag.data_type),
                behavior=sim_tag.behavior or "immediate",
                address_strategy=sim_tag.address_strategy or "generic",
                address=sim_tag.address or {},
                mode_config=sim_tag.mode_config,
                enabled=sim_tag.enabled,
                config={},
            )
        )
    TagConfig.objects.bulk_create(configs, ignore_conflicts=True, batch_size=5000)
    pending_sim_tags.clear()


def backfill_sim_device_tag_config(apps, schema_editor):
    Device = apps.get_model("base", "Device")
    Tag = apps.get_model("base", "Tag")
    SimDevice = apps.get_model("base", "SimDevice")
    SimDeviceTag = apps.get_model("base", "SimDeviceTag")
    FieldDevice = apps.get_model("base", "FieldDevice")
    FieldTag = apps.get_model("base", "FieldTag")
    DeviceConfig = apps.get_model("sim", "DeviceConfig")
    TagConfig = apps.get_model("sim", "TagConfig")

    sim_devices = list(SimDevice.objects.select_related("provider", "provider__sim_server", "driver"))
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
            "provider", "device", "device__provider", "tag_node"
        )
    }

    sim_device_config_ids = {}
    for sim_device in sim_devices:
        base_device = _get_base_device(Device, namespace=_device_namespace_from_sim(sim_device), name=sim_device.name)
        device_config = _upsert_device_config(
            DeviceConfig,
            base_device=base_device,
            defaults={
                "source_provider": sim_device.provider,
                "sim_server": sim_device.provider.sim_server,
                "driver": sim_device.driver,
                "browse_path": sim_device.provider.name,
                "mode": sim_device.mode or "standard",
                "response_delay_ms": sim_device.response_delay_ms,
                "source_status": sim_device.source_status or "",
                "source_detail": sim_device.source_detail or "",
                "enabled": sim_device.enabled,
                "config": sim_device.config or {},
            },
        )
        sim_device_config_ids[sim_device.id] = device_config.id

    for field_device in FieldDevice.objects.select_related("endpoint"):
        namespace, name = _device_namespace_from_field(field_device, sim_devices_by_id)
        base_device = _get_base_device(Device, namespace=namespace, name=name)
        _upsert_device_config(
            DeviceConfig,
            base_device=base_device,
            defaults={
                "endpoint": field_device.endpoint,
                "browse_path": field_device.browse_path or "Devices",
                "mode": _field_device_mode(field_device),
                "response_delay_ms": (field_device.config or {}).get("response_delay_ms", 0) or 0,
                "enabled": field_device.enabled,
                "config": field_device.config or {},
            },
        )

    pending_sim_tags = []
    for sim_tag in SimDeviceTag.objects.select_related("provider", "device").iterator(chunk_size=5000):
        pending_sim_tags.append(sim_tag)
        if len(pending_sim_tags) >= 5000:
            _flush_sim_tag_configs(TagConfig, Tag, pending_sim_tags, sim_device_config_ids)
    _flush_sim_tag_configs(TagConfig, Tag, pending_sim_tags, sim_device_config_ids)

    for field_tag in field_tags:
        namespace, name = _device_namespace_from_field(field_tag.device, sim_devices_by_id)
        base_device = _get_base_device(Device, namespace=namespace, name=name)
        sim_device = DeviceConfig.objects.get(base_device=base_device)
        provider, tagpath, sim_tag = _sim_tag_identity_from_field(field_tag, sim_tags_by_id)
        base_tag = _get_base_tag(Tag, provider=provider, tagpath=tagpath)
        metadata = field_tag.config or {}
        _upsert_tag_config(
            TagConfig,
            sim_device=sim_device,
            base_tag=base_tag,
            defaults={
                "source_tag_node": sim_tag.tag_node if sim_tag is not None else None,
                "source_path": sim_tag.source_path if sim_tag is not None else field_tag.description or "",
                "tag_name": field_tag.name,
                "simulation_type": field_tag.simulation_type or _simulation_type_for_data_type(field_tag.data_type),
                "min_value": field_tag.min_value,
                "max_value": field_tag.max_value,
                "variance": field_tag.variance,
                "initial_value": field_tag.initial_value or "",
                "behavior": metadata.get("behavior") or "immediate",
                "mode_config": metadata.get("mode_config"),
                "enabled": field_tag.enabled,
                "config": metadata,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0010_kernel_device_tag"),
        ("sim", "0007_simjob"),
    ]

    operations = [
        migrations.RunSQL(sql="CREATE SCHEMA IF NOT EXISTS sim;", reverse_sql=migrations.RunSQL.noop),
        migrations.CreateModel(
            name="DeviceConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("browse_path", models.CharField(default="Devices", max_length=1000)),
                ("mode", models.CharField(choices=[("standard", "Standard"), ("slow_network", "Slow network")], default="standard", max_length=40)),
                ("response_delay_ms", models.PositiveIntegerField(default=0)),
                ("source_status", models.CharField(blank=True, max_length=255)),
                ("source_detail", models.TextField(blank=True)),
                ("enabled", models.BooleanField(default=True)),
                ("config", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("base_device", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="sim_config", to="base.device")),
                ("driver", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sim_device_configs", to="base.simdriver")),
                ("endpoint", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sim_device_configs", to="base.fieldendpoint")),
                ("sim_server", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sim_device_configs", to="base.simserver")),
                ("source_provider", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sim_device_configs", to="base.tagprovider")),
            ],
            options={
                "db_table": '"sim"."device"',
                "ordering": ["base_device__namespace", "base_device__name"],
            },
        ),
        migrations.CreateModel(
            name="TagConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_path", models.CharField(blank=True, max_length=1200)),
                ("tag_name", models.CharField(blank=True, max_length=255)),
                ("simulation_type", models.CharField(choices=[("toggle", "Toggle"), ("ramp", "Ramp"), ("wave", "Wave"), ("random_walk", "Random walk"), ("static", "Static")], default="ramp", max_length=40)),
                ("min_value", models.FloatField(blank=True, null=True)),
                ("max_value", models.FloatField(blank=True, null=True)),
                ("variance", models.FloatField(default=0.0)),
                ("initial_value", models.CharField(blank=True, max_length=255)),
                ("behavior", models.CharField(default="immediate", max_length=40)),
                ("address_strategy", models.CharField(default="generic", max_length=80)),
                ("address", models.JSONField(blank=True, default=dict)),
                ("mode_config", models.JSONField(blank=True, null=True)),
                ("enabled", models.BooleanField(default=True)),
                ("config", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("base_tag", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="sim_config", to="base.tag")),
                ("sim_device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tags", to="sim.deviceconfig")),
                ("source_tag_node", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sim_tag_configs", to="base.tagnode")),
            ],
            options={
                "db_table": '"sim"."tag"',
                "ordering": ["sim_device", "base_tag__name"],
            },
        ),
        migrations.AddIndex(
            model_name="deviceconfig",
            index=models.Index(fields=["endpoint"], name="sim_device_endpoint_idx"),
        ),
        migrations.AddIndex(
            model_name="deviceconfig",
            index=models.Index(fields=["source_provider"], name="sim_device_provider_idx"),
        ),
        migrations.AddIndex(
            model_name="deviceconfig",
            index=models.Index(fields=["enabled"], name="sim_device_enabled_idx"),
        ),
        migrations.AddConstraint(
            model_name="tagconfig",
            constraint=models.UniqueConstraint(fields=("sim_device", "base_tag"), name="unique_sim_device_tag"),
        ),
        migrations.AddIndex(
            model_name="tagconfig",
            index=models.Index(fields=["sim_device", "enabled"], name="sim_tag_device_enabled_idx"),
        ),
        migrations.AddIndex(
            model_name="tagconfig",
            index=models.Index(fields=["simulation_type"], name="sim_tag_sim_type_idx"),
        ),
        migrations.RunPython(backfill_sim_device_tag_config, migrations.RunPython.noop),
    ]
