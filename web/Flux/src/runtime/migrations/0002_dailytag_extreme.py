import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("runtime", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DailyTagExtreme",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True)),
                ("min_value", models.FloatField()),
                ("max_value", models.FloatField()),
                ("sample_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tag",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_extremes",
                        to="runtime.runtimetag",
                    ),
                ),
            ],
            options={
                "ordering": ["-date", "tag__asset_name", "tag__display_name"],
                "indexes": [models.Index(fields=["tag", "-date"], name="runtime_dai_tag_id_2b57d3_idx")],
                "constraints": [models.UniqueConstraint(fields=("tag", "date"), name="unique_daily_tag_extreme")],
            },
        ),
    ]
