from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("bridge", "0002_rename_ignition_bridge_table"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    CREATE SCHEMA IF NOT EXISTS bridge;
                    ALTER TABLE bridge_ignition_bridge SET SCHEMA bridge;
                    ALTER TABLE bridge.bridge_ignition_bridge RENAME TO ignition_bridge;
                    """,
                    reverse_sql="""
                    ALTER TABLE bridge.ignition_bridge SET SCHEMA public;
                    ALTER TABLE bridge_ignition_bridge RENAME TO dashboard_ignitionbridgeconfig;
                    """,
                ),
            ],
            state_operations=[
                migrations.AlterModelTable(
                    name="ignitionbridgeconfig",
                    table='"bridge"."ignition_bridge"',
                ),
            ],
        ),
    ]
