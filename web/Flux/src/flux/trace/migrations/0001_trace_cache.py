import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("runtime", "0004_rename_runtime_dai_tag_id_2b57d3_idx_runtime_dai_tag_id_bd3777_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="TraceProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=120, unique=True)),
                ("label", models.CharField(max_length=255)),
                ("enabled", models.BooleanField(default=True)),
                ("cache_enabled", models.BooleanField(default=True)),
                ("cache_window_minutes", models.PositiveIntegerField(default=1440)),
                ("sync_interval_seconds", models.PositiveIntegerField(default=60)),
                ("history_provider", models.CharField(default="Core Historian", max_length=255)),
                ("max_query_points", models.PositiveIntegerField(default=500000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["key"]},
        ),
        migrations.CreateModel(
            name="TraceSignal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(blank=True, max_length=255)),
                ("unit", models.CharField(blank=True, max_length=80)),
                ("axis_key", models.SlugField(default="process", max_length=80)),
                ("axis_label", models.CharField(blank=True, max_length=120)),
                ("axis_unit", models.CharField(blank=True, max_length=80)),
                ("range_min", models.FloatField(blank=True, null=True)),
                ("range_max", models.FloatField(blank=True, null=True)),
                ("color", models.CharField(blank=True, max_length=40)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("default_visible", models.BooleanField(default=True)),
                ("cache_enabled", models.BooleanField(default=True)),
                ("source_path", models.CharField(blank=True, max_length=1200)),
                ("history_provider", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="signals", to="trace.traceprofile")),
                ("tag", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trace_signals", to="runtime.runtimetag")),
            ],
            options={"ordering": ["profile__key", "sort_order", "label", "tag__display_name"]},
        ),
        migrations.CreateModel(
            name="TraceCacheCursor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_timestamp", models.DateTimeField(blank=True, null=True)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("signal", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="cache_cursor", to="trace.tracesignal")),
            ],
            options={"ordering": ["signal__profile__key", "signal__sort_order"]},
        ),
        migrations.CreateModel(
            name="TraceCachePoint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField()),
                ("value_float", models.FloatField()),
                ("quality_code", models.CharField(default="Good", max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("signal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cache_points", to="trace.tracesignal")),
            ],
            options={"ordering": ["-timestamp"]},
        ),
        migrations.AddIndex(model_name="tracesignal", index=models.Index(fields=["profile", "cache_enabled", "sort_order"], name="trace_sig_profile_cache_idx")),
        migrations.AddIndex(model_name="tracesignal", index=models.Index(fields=["tag"], name="trace_signal_tag_idx")),
        migrations.AddConstraint(model_name="tracesignal", constraint=models.UniqueConstraint(fields=("profile", "tag"), name="unique_trace_signal_profile_tag")),
        migrations.AddIndex(model_name="tracecachepoint", index=models.Index(fields=["signal", "-timestamp"], name="trace_cache_sig_time_idx")),
        migrations.AddIndex(model_name="tracecachepoint", index=models.Index(fields=["timestamp"], name="trace_cache_timestamp_idx")),
        migrations.AddConstraint(model_name="tracecachepoint", constraint=models.UniqueConstraint(fields=("signal", "timestamp"), name="unique_trace_cache_signal_timestamp")),
    ]
