from django.db import migrations


def migrate_provider_selection_rows(apps, schema_editor):
    SimProviderSelection = apps.get_model("sim", "SimProviderSelection")
    Provider = apps.get_model("sim", "Provider")
    ProviderSelection = apps.get_model("sim", "ProviderSelection")

    for legacy in SimProviderSelection.objects.filter(enabled=True).iterator():
        provider, _created = Provider.objects.get_or_create(
            name=legacy.provider,
            defaults={
                "source": "json_upload",
                "source_name": "legacy_ui_selection",
                "source_sha256": "",
            },
        )
        ProviderSelection.objects.update_or_create(
            provider=provider,
            purpose="sim",
            path=legacy.path,
            defaults={"enabled": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("sim", "0015_endpoint_schema"),
    ]

    operations = [
        migrations.RunPython(migrate_provider_selection_rows, migrations.RunPython.noop),
        migrations.DeleteModel(name="SimProviderSelection"),
    ]
