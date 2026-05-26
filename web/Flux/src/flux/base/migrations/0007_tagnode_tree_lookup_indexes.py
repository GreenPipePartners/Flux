from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0006_simserver_tagprovider"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="tagnode",
            index=models.Index(fields=["provider", "parent", "sort_order"], name="base_tagnod_provide_db4760_idx"),
        ),
        migrations.AddIndex(
            model_name="tagnode",
            index=models.Index(fields=["provider", "depth", "sort_order"], name="base_tagnod_provide_ac3d40_idx"),
        ),
    ]
