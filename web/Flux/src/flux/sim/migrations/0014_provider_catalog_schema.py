import django.db.models.deletion
from django.db import migrations, models


FORWARD_SQL = """
CREATE SCHEMA IF NOT EXISTS "sim";

ALTER TABLE IF EXISTS "public"."base_simserver" SET SCHEMA "sim";
ALTER TABLE IF EXISTS "sim"."base_simserver" RENAME TO "server";

ALTER TABLE IF EXISTS "public"."base_simdriver" SET SCHEMA "sim";
ALTER TABLE IF EXISTS "sim"."base_simdriver" RENAME TO "driver";

ALTER TABLE IF EXISTS "public"."base_tagprovider" SET SCHEMA "sim";
ALTER TABLE IF EXISTS "sim"."base_tagprovider" RENAME TO "provider";

ALTER TABLE IF EXISTS "public"."base_tagnode" SET SCHEMA "sim";
ALTER TABLE IF EXISTS "sim"."base_tagnode" RENAME TO "provider_node";

ALTER TABLE IF EXISTS "public"."base_tagselection" SET SCHEMA "sim";
ALTER TABLE IF EXISTS "sim"."base_tagselection" RENAME TO "provider_selection";
"""


REVERSE_SQL = """
ALTER TABLE IF EXISTS "sim"."provider_selection" RENAME TO "base_tagselection";
ALTER TABLE IF EXISTS "sim"."base_tagselection" SET SCHEMA "public";

ALTER TABLE IF EXISTS "sim"."provider_node" RENAME TO "base_tagnode";
ALTER TABLE IF EXISTS "sim"."base_tagnode" SET SCHEMA "public";

ALTER TABLE IF EXISTS "sim"."provider" RENAME TO "base_tagprovider";
ALTER TABLE IF EXISTS "sim"."base_tagprovider" SET SCHEMA "public";

ALTER TABLE IF EXISTS "sim"."driver" RENAME TO "base_simdriver";
ALTER TABLE IF EXISTS "sim"."base_simdriver" SET SCHEMA "public";

ALTER TABLE IF EXISTS "sim"."server" RENAME TO "base_simserver";
ALTER TABLE IF EXISTS "sim"."base_simserver" SET SCHEMA "public";
"""


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0012_entity"),
        ("sim", "0013_tagconfig_behavior_choices"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)],
            state_operations=[
                migrations.CreateModel(
                    name="Server",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("name", models.CharField(max_length=120, unique=True)),
                        ("endpoint_url", models.CharField(default="opc.tcp://0.0.0.0:4840/flux/sim", max_length=255)),
                        ("application_uri", models.CharField(default="urn:flux:sim", max_length=255)),
                        ("product_uri", models.CharField(default="urn:flux:sim", max_length=255)),
                        ("namespace_uri", models.CharField(default="urn:flux:sim", max_length=255)),
                        ("enabled", models.BooleanField(default=True)),
                        ("security_policy", models.CharField(default="None", max_length=120)),
                        ("description", models.TextField(blank=True)),
                        ("config", models.JSONField(blank=True, default=dict)),
                    ],
                    options={"db_table": '"sim"."server"', "ordering": ["name"]},
                ),
                migrations.CreateModel(
                    name="Driver",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("key", models.CharField(max_length=80, unique=True)),
                        ("label", models.CharField(max_length=120)),
                        ("strategy_key", models.CharField(default="generic", max_length=80)),
                        ("ignition_driver_names", models.JSONField(blank=True, default=list)),
                        ("description", models.TextField(blank=True)),
                    ],
                    options={"db_table": '"sim"."driver"', "ordering": ["key"]},
                ),
                migrations.CreateModel(
                    name="Provider",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("name", models.CharField(max_length=120, unique=True)),
                        ("source", models.CharField(choices=[("json_upload", "JSON upload"), ("ignition_provider", "Ignition provider")], max_length=40)),
                        ("source_name", models.CharField(blank=True, max_length=255)),
                        ("source_sha256", models.CharField(max_length=64)),
                        ("root_tag_type", models.CharField(default="Provider", max_length=80)),
                        ("total_nodes", models.PositiveIntegerField(default=0)),
                        ("folder_count", models.PositiveIntegerField(default=0)),
                        ("atomic_tag_count", models.PositiveIntegerField(default=0)),
                        ("udt_instance_count", models.PositiveIntegerField(default=0)),
                        ("udt_type_count", models.PositiveIntegerField(default=0)),
                        ("imported_at", models.DateTimeField(auto_now=True)),
                        ("sim_server", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="tag_providers", to="sim.server")),
                    ],
                    options={"db_table": '"sim"."provider"', "ordering": ["name"]},
                ),
                migrations.CreateModel(
                    name="ProviderNode",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("path", models.CharField(max_length=1200)),
                        ("name", models.CharField(blank=True, max_length=255)),
                        ("tag_type", models.CharField(max_length=80)),
                        ("data_type", models.CharField(blank=True, max_length=80)),
                        ("value_source", models.CharField(blank=True, max_length=80)),
                        ("type_id", models.CharField(blank=True, max_length=1200)),
                        ("opc_server", models.CharField(blank=True, max_length=255)),
                        ("opc_item_path", models.CharField(blank=True, max_length=1200)),
                        ("source_tag_path", models.CharField(blank=True, max_length=1200)),
                        ("expression", models.TextField(blank=True)),
                        ("engineering_units", models.CharField(blank=True, max_length=80)),
                        ("documentation", models.TextField(blank=True)),
                        ("tooltip", models.TextField(blank=True)),
                        ("parameters", models.JSONField(blank=True, null=True)),
                        ("value", models.JSONField(blank=True, null=True)),
                        ("raw_config", models.JSONField(blank=True, default=dict)),
                        ("depth", models.PositiveSmallIntegerField(default=0)),
                        ("sort_order", models.PositiveIntegerField(default=0)),
                        ("has_children", models.BooleanField(default=False)),
                        ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="sim.providernode")),
                        ("provider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="nodes", to="sim.provider")),
                    ],
                    options={
                        "db_table": '"sim"."provider_node"',
                        "ordering": ["provider", "depth", "sort_order", "name"],
                        "indexes": [
                            models.Index(fields=["provider", "parent"], name="base_tagnod_provide_575f83_idx"),
                            models.Index(fields=["provider", "parent", "sort_order"], name="base_tagnod_provide_db4760_idx"),
                            models.Index(fields=["provider", "depth", "sort_order"], name="base_tagnod_provide_ac3d40_idx"),
                            models.Index(fields=["provider", "tag_type"], name="base_tagnod_provide_4968b0_idx"),
                            models.Index(fields=["provider", "value_source"], name="base_tagnod_provide_216a5b_idx"),
                            models.Index(fields=["provider", "data_type"], name="base_tagnod_provide_970d48_idx"),
                        ],
                        "constraints": [models.UniqueConstraint(fields=("provider", "path"), name="unique_base_tag_node_path")],
                    },
                ),
                migrations.CreateModel(
                    name="ProviderSelection",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("path", models.CharField(max_length=1200)),
                        ("purpose", models.CharField(choices=[("sim", "Simulation"), ("runtime", "Runtime"), ("field", "Field")], default="sim", max_length=40)),
                        ("enabled", models.BooleanField(default=True)),
                        ("config", models.JSONField(blank=True, default=dict)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("provider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="selections", to="sim.provider")),
                    ],
                    options={
                        "db_table": '"sim"."provider_selection"',
                        "ordering": ["provider", "purpose", "path"],
                        "constraints": [models.UniqueConstraint(fields=("provider", "purpose", "path"), name="unique_base_tag_selection")],
                    },
                ),
                migrations.AlterField(
                    model_name="deviceconfig",
                    name="driver",
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sim_device_configs", to="sim.driver"),
                ),
                migrations.AlterField(
                    model_name="deviceconfig",
                    name="sim_server",
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sim_device_configs", to="sim.server"),
                ),
                migrations.AlterField(
                    model_name="deviceconfig",
                    name="source_provider",
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sim_device_configs", to="sim.provider"),
                ),
                migrations.AlterField(
                    model_name="tagconfig",
                    name="source_tag_node",
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sim_tag_configs", to="sim.providernode"),
                ),
            ],
        ),
    ]
