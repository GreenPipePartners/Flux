import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trace", "0001_trace_cache"),
    ]

    operations = [
        migrations.CreateModel(
            name="TraceAnnotation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("marker_id", models.PositiveIntegerField(blank=True, null=True)),
                ("marker_time", models.DateTimeField()),
                ("text", models.TextField()),
                ("source", models.CharField(default="flux.trace", max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("profile", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="annotations", to="trace.traceprofile")),
            ],
            options={"ordering": ["-marker_time", "-id"]},
        ),
        migrations.CreateModel(
            name="TraceAnnotationTarget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("historian_path", models.CharField(max_length=1200)),
                ("ignition_storage_id", models.UUIDField(unique=True)),
                ("quality_code", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("annotation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="targets", to="trace.traceannotation")),
                ("signal", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="annotation_targets", to="trace.tracesignal")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddIndex(model_name="traceannotation", index=models.Index(fields=["profile", "-marker_time"], name="trace_annot_profile_time_idx")),
        migrations.AddIndex(model_name="traceannotationtarget", index=models.Index(fields=["annotation"], name="trace_annotation_target_idx")),
        migrations.AddIndex(model_name="traceannotationtarget", index=models.Index(fields=["signal"], name="trace_annotation_signal_idx")),
    ]
