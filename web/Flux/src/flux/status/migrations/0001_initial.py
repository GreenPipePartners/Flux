from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("base", "0012_entity"),
    ]

    operations = [
        migrations.RunSQL(sql="CREATE SCHEMA IF NOT EXISTS status;", reverse_sql=migrations.RunSQL.noop),
        migrations.CreateModel(
            name="LatestStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status_kind", models.CharField(choices=[("connectivity", "Connectivity"), ("sampling", "Sampling"), ("freshness", "Freshness"), ("quality", "Quality"), ("worker", "Worker"), ("storage", "Storage"), ("configuration", "Configuration")], max_length=40)),
                ("observed_state", models.CharField(choices=[("ok", "OK"), ("warning", "Warning"), ("error", "Error"), ("stale", "Stale"), ("missing", "Missing"), ("unknown", "Unknown"), ("disabled", "Disabled")], default="unknown", max_length=40)),
                ("severity", models.CharField(choices=[("ok", "OK"), ("warning", "Warning"), ("error", "Error"), ("unknown", "Unknown")], default="unknown", max_length=20)),
                ("summary", models.CharField(blank=True, max_length=255)),
                ("detail", models.TextField(blank=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("stale_after_seconds", models.PositiveIntegerField(blank=True, null=True)),
                ("source", models.CharField(max_length=120)),
                ("source_instance", models.CharField(blank=True, max_length=180)),
                ("evidence", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="latest_statuses", to="base.entity")),
            ],
            options={
                "db_table": '"status"."latest"',
                "ordering": ["entity", "status_kind", "source", "source_instance"],
            },
        ),
        migrations.AddConstraint(
            model_name="lateststatus",
            constraint=models.UniqueConstraint(fields=("entity", "status_kind", "source", "source_instance"), name="unique_status_latest_entity_kind_source"),
        ),
        migrations.AddIndex(
            model_name="lateststatus",
            index=models.Index(fields=["entity", "status_kind"], name="status_latest_entity_kind_idx"),
        ),
        migrations.AddIndex(
            model_name="lateststatus",
            index=models.Index(fields=["observed_state"], name="status_latest_observed_idx"),
        ),
        migrations.AddIndex(
            model_name="lateststatus",
            index=models.Index(fields=["severity"], name="status_latest_severity_idx"),
        ),
        migrations.AddIndex(
            model_name="lateststatus",
            index=models.Index(fields=["last_seen_at"], name="status_latest_seen_idx"),
        ),
    ]
