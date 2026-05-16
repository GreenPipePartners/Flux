from django.db import migrations


def ensure_ignition_bridge_table(apps, schema_editor):
    IgnitionBridgeConfig = apps.get_model("dashboard", "IgnitionBridgeConfig")
    table_name = IgnitionBridgeConfig._meta.db_table
    existing_tables = schema_editor.connection.introspection.table_names()
    if table_name not in existing_tables:
        schema_editor.create_model(IgnitionBridgeConfig)


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(ensure_ignition_bridge_table, migrations.RunPython.noop),
    ]
