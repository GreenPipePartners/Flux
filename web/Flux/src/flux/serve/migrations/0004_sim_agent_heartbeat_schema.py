import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


FORWARD_SQL = """
CREATE SCHEMA IF NOT EXISTS "serve";

ALTER TABLE IF EXISTS "public"."base_fieldagentheartbeat" SET SCHEMA "serve";
ALTER TABLE IF EXISTS "serve"."base_fieldagentheartbeat" RENAME TO "sim_agent_heartbeat";
"""


REVERSE_SQL = """
ALTER TABLE IF EXISTS "serve"."sim_agent_heartbeat" RENAME TO "base_fieldagentheartbeat";
ALTER TABLE IF EXISTS "serve"."base_fieldagentheartbeat" SET SCHEMA "public";
"""


class Migration(migrations.Migration):
    dependencies = [
        ("serve", "0003_linux_only_serve_platform"),
        ("sim", "0015_endpoint_schema"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)],
            state_operations=[
                migrations.CreateModel(
                    name="SimAgentHeartbeat",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("instance_id", models.CharField(max_length=120)),
                        ("process_id", models.PositiveIntegerField(blank=True, null=True)),
                        ("version", models.CharField(blank=True, max_length=80)),
                        ("started_at", models.DateTimeField(blank=True, null=True)),
                        ("last_seen_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                        ("current_node_count", models.PositiveIntegerField(default=0)),
                        ("last_error", models.TextField(blank=True)),
                        ("endpoint", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="heartbeats", to="sim.endpoint")),
                    ],
                    options={
                        "db_table": '"serve"."sim_agent_heartbeat"',
                        "ordering": ["endpoint", "instance_id"],
                        "constraints": [models.UniqueConstraint(fields=("endpoint", "instance_id"), name="unique_base_field_agent_instance")],
                    },
                ),
            ],
        ),
    ]
