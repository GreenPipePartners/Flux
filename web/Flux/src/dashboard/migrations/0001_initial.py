from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="IgnitionBridgeConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="default", max_length=64, unique=True)),
                ("base_url", models.URLField(default="http://localhost:8088/system/webdev/flux")),
                ("token", models.CharField(blank=True, max_length=255)),
                ("last_test_ok", models.BooleanField(default=False)),
                ("last_test_message", models.CharField(blank=True, max_length=255)),
                ("last_test_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Ignition bridge config",
                "verbose_name_plural": "Ignition bridge config",
            },
        ),
    ]
