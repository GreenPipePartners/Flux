from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sim", "0002_seed_default_sim_config"),
    ]

    operations = [
        migrations.CreateModel(
            name="SimProviderSelection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=120)),
                ("path", models.CharField(max_length=1200)),
                ("enabled", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["provider", "path"]},
        ),
        migrations.AddConstraint(
            model_name="simproviderselection",
            constraint=models.UniqueConstraint(
                fields=("provider", "path"), name="unique_sim_provider_selection"
            ),
        ),
    ]
