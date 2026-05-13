from django.db import migrations, models


def seed_default_scheduler(apps, schema_editor):
    scheduler_config = apps.get_model("runtime", "RuntimeSchedulerConfig")
    scheduler_config.objects.get_or_create(name="default")


class Migration(migrations.Migration):

    dependencies = [
        ("runtime", "0002_dailytag_extreme"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimetag",
            name="balancer_code",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.CreateModel(
            name="RuntimeSchedulerConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="default", max_length=80, unique=True)),
                ("hot_interval_seconds", models.PositiveSmallIntegerField(default=1)),
                ("warm_interval_seconds", models.PositiveSmallIntegerField(default=10)),
                ("warm_cycles_after_hot", models.PositiveSmallIntegerField(default=1)),
                ("cold_bucket_count", models.PositiveSmallIntegerField(default=60)),
                ("current_balancer_code", models.PositiveSmallIntegerField(default=1)),
                ("balancer_increment", models.PositiveSmallIntegerField(default=1)),
                ("demand_lease_seconds", models.PositiveSmallIntegerField(default=5)),
                ("enabled", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.RunPython(seed_default_scheduler, migrations.RunPython.noop),
    ]
