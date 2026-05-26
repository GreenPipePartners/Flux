from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("build", "0002_alter_buildrun_target_hmimapselection"),
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
                ],
                max_length=80,
            ),
        ),
    ]
