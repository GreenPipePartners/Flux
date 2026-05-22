from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("field", "0003_fielddevice_fieldtag_and_more"),
        ("sim", "0005_simtag_mode_config_write_to_other"),
    ]

    operations = [
        migrations.DeleteModel(name="SimTag"),
        migrations.DeleteModel(name="SimSchedule"),
        migrations.DeleteModel(name="SimHistoryBackfill"),
    ]
