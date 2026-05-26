from django.db import migrations, models


FORWARD_SQL = """
CREATE SCHEMA IF NOT EXISTS "sim";

ALTER TABLE IF EXISTS "public"."base_fieldendpoint" SET SCHEMA "sim";
ALTER TABLE IF EXISTS "sim"."base_fieldendpoint" RENAME TO "endpoint";
"""


REVERSE_SQL = """
ALTER TABLE IF EXISTS "sim"."endpoint" RENAME TO "base_fieldendpoint";
ALTER TABLE IF EXISTS "sim"."base_fieldendpoint" SET SCHEMA "public";
"""


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0013_remove_sim_catalog_state"),
        ("sim", "0014_provider_catalog_schema"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)],
            state_operations=[
                migrations.CreateModel(
                    name="Endpoint",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("name", models.CharField(max_length=120, unique=True)),
                        ("endpoint_url", models.CharField(default="opc.tcp://0.0.0.0:4840/flux/field", max_length=255)),
                        ("application_uri", models.CharField(default="urn:flux:field", max_length=255)),
                        ("product_uri", models.CharField(default="urn:flux:field", max_length=255)),
                        ("namespace_uri", models.CharField(default="urn:flux:field:sim", max_length=255)),
                        ("enabled", models.BooleanField(default=True)),
                        ("security_policy", models.CharField(default="None", max_length=120)),
                        ("status", models.CharField(choices=[("disabled", "Disabled"), ("starting", "Starting"), ("running", "Running"), ("error", "Error")], default="disabled", max_length=20)),
                        ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                        ("last_error", models.TextField(blank=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={"db_table": '"sim"."endpoint"', "ordering": ["name"]},
                ),
                migrations.AlterField(
                    model_name="deviceconfig",
                    name="endpoint",
                    field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="sim_device_configs", to="sim.endpoint"),
                ),
            ],
        ),
    ]
