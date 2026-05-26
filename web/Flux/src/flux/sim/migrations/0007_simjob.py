from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sim", "0006_remove_legacy_memory_sim"),
    ]

    operations = [
        migrations.CreateModel(
            name="SimJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("import_provider_json", "Import provider JSON"), ("import_provider_ignition", "Import provider from Ignition"), ("remove_ignition_tags", "Remove Ignition sim tags"), ("apply_selection", "Apply sim selection")], max_length=80)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("complete", "Complete"), ("failed", "Failed")], default="queued", max_length=20)),
                ("provider", models.CharField(blank=True, max_length=120)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("input_path", models.CharField(blank=True, max_length=1200)),
                ("progress_current", models.PositiveIntegerField(default=0)),
                ("progress_total", models.PositiveIntegerField(default=0)),
                ("progress_label", models.CharField(blank=True, max_length=255)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="simjob",
            index=models.Index(fields=["kind", "status"], name="sim_job_kind_status_idx"),
        ),
        migrations.AddIndex(
            model_name="simjob",
            index=models.Index(fields=["status", "created_at"], name="sim_job_status_created_idx"),
        ),
    ]
