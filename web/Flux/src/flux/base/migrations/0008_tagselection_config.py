from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0007_tagnode_tree_lookup_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="tagselection",
            name="config",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
