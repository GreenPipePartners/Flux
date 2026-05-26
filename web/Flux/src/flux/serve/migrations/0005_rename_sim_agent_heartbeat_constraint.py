from django.db import migrations, models


FORWARD_SQL = """
ALTER TABLE "serve"."sim_agent_heartbeat" RENAME CONSTRAINT "unique_base_field_agent_instance" TO "unique_serve_sim_agent_instance";
ALTER TABLE "serve"."sim_agent_heartbeat" RENAME CONSTRAINT "base_fieldagentheart_endpoint_id_b69774f9_fk_base_fiel" TO "serve_sim_agent_heartbeat_endpoint_id_fk";
ALTER INDEX "serve"."base_fieldagentheartbeat_endpoint_id_b69774f9" RENAME TO "serve_sim_agent_heartbeat_endpoint_id_idx";
ALTER INDEX "serve"."base_fieldagentheartbeat_last_seen_at_f53a6ba1" RENAME TO "serve_sim_agent_heartbeat_seen_idx";
"""


REVERSE_SQL = """
ALTER INDEX "serve"."serve_sim_agent_heartbeat_seen_idx" RENAME TO "base_fieldagentheartbeat_last_seen_at_f53a6ba1";
ALTER INDEX "serve"."serve_sim_agent_heartbeat_endpoint_id_idx" RENAME TO "base_fieldagentheartbeat_endpoint_id_b69774f9";
ALTER TABLE "serve"."sim_agent_heartbeat" RENAME CONSTRAINT "serve_sim_agent_heartbeat_endpoint_id_fk" TO "base_fieldagentheart_endpoint_id_b69774f9_fk_base_fiel";
ALTER TABLE "serve"."sim_agent_heartbeat" RENAME CONSTRAINT "unique_serve_sim_agent_instance" TO "unique_base_field_agent_instance";
"""


class Migration(migrations.Migration):
    dependencies = [
        ("serve", "0004_sim_agent_heartbeat_schema"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)],
            state_operations=[
                migrations.RemoveConstraint(model_name="simagentheartbeat", name="unique_base_field_agent_instance"),
                migrations.AddConstraint(
                    model_name="simagentheartbeat",
                    constraint=models.UniqueConstraint(fields=("endpoint", "instance_id"), name="unique_serve_sim_agent_instance"),
                ),
            ],
        ),
    ]
