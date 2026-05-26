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


def _field_tag_identity(field_tag, sim_tags_by_id):
    metadata = field_tag.config or {}
    sim_tag_id = metadata.get("sim_device_tag_id") if metadata.get("source") == "sim_device_tag" else None
    sim_tag = sim_tags_by_id.get(sim_tag_id)
    if sim_tag is not None:
        return sim_tag.provider.name, sim_tag.source_path or "%s/%s" % (sim_tag.device.name, sim_tag.tag_name)
    provider = field_tag.device.endpoint.name if field_tag.device.endpoint_id else field_tag.device.browse_path
    return provider, "%s/%s" % (field_tag.device.name, field_tag.name)


def reconcile_materialized_enabled(apps, schema_editor):
    SimDevice = apps.get_model("base", "SimDevice")
    SimDeviceTag = apps.get_model("base", "SimDeviceTag")
    FieldTag = apps.get_model("base", "FieldTag")
    TagConfig = apps.get_model("sim", "TagConfig")

    sim_devices_by_id = {device.id: device for device in SimDevice.objects.select_related("provider")}
    field_tags = list(FieldTag.objects.select_related("device", "device__endpoint"))
    linked_sim_tag_ids = set()
    for field_tag in field_tags:
        metadata = field_tag.config or {}
        if metadata.get("source") == "sim_device_tag" and metadata.get("sim_device_tag_id"):
            linked_sim_tag_ids.add(metadata["sim_device_tag_id"])
    sim_tags_by_id = {
        tag.id: tag
        for tag in SimDeviceTag.objects.filter(id__in=linked_sim_tag_ids).select_related("provider", "device")
    }

    TagConfig.objects.filter(materialized=True).update(enabled=False)
    for field_tag in field_tags:
        if not field_tag.enabled:
            continue
        provider, tagpath = _field_tag_identity(field_tag, sim_tags_by_id)
        namespace, device_name = _device_namespace_from_field(field_tag.device, sim_devices_by_id)
        TagConfig.objects.filter(
            base_tag__provider=provider,
            base_tag__tagpath=tagpath,
            sim_device__base_device__namespace=namespace,
            sim_device__base_device__name=device_name,
            materialized=True,
        ).update(enabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ("sim", "0009_tagconfig_materialized"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tagconfig",
            name="base_tag",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sim_configs", to="base.tag"),
        ),
        migrations.RunPython(reconcile_materialized_enabled, migrations.RunPython.noop),
    ]
