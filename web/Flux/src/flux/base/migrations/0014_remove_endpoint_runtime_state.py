from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0013_remove_sim_catalog_state"),
        ("serve", "0004_sim_agent_heartbeat_schema"),
        ("sim", "0015_endpoint_schema"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="FieldAgentHeartbeat"),
                migrations.DeleteModel(name="FieldEndpoint"),
            ],
        ),
    ]
