from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("bridge", "0001_dashboard_table_state"),
        ("dashboard", "0003_ignitionbridgeconfig_role"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[migrations.DeleteModel(name="IgnitionBridgeConfig")],
        ),
    ]
