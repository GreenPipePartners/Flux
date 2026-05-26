from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("plane", "0004_sample_backfill_trace_cache"),
        ("trace", "0003_signal_series"),
    ]

    operations = [migrations.DeleteModel(name="TraceCachePoint")]
