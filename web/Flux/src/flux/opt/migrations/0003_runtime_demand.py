import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("opt", "0002_seed_refresh_lanes"),
    ]

    operations = [
        migrations.CreateModel(
            name="RuntimeDemand",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_key", models.CharField(max_length=180)),
                ("target_path", models.CharField(max_length=1124)),
                ("claimed_by", models.CharField(default="flux-demand-ui", max_length=120)),
                ("touched_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "ordering": ["expires_at", "source_key", "target_path"],
            },
        ),
        migrations.AddIndex(
            model_name="runtimedemand",
            index=models.Index(fields=["expires_at", "target_path"], name="runtime_demand_active_idx"),
        ),
        migrations.AddConstraint(
            model_name="runtimedemand",
            constraint=models.UniqueConstraint(fields=("source_key", "target_path"), name="unique_runtime_demand_source_path"),
        ),
    ]
