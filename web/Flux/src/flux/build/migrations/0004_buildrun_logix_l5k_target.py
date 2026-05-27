from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("build", "0003_buildrun_logix_l5x_target"),
    ]

    operations = [
        migrations.AlterField(
            model_name="buildrun",
            name="target",
            field=models.CharField(
                choices=[
                    ("ignition_tags", "Ignition Tags"),
                    ("hmi_symbolic_map", "HMI Symbolic Map"),
                    ("logix_l5x", "Logix L5X"),
                    ("logix_l5k", "Logix L5K"),
                ],
                max_length=80,
            ),
        ),
    ]
