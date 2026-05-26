from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("bridge", "0001_dashboard_table_state"),
    ]

    operations = [
        migrations.AlterModelTable(
            name="ignitionbridgeconfig",
            table="bridge_ignition_bridge",
        ),
    ]
