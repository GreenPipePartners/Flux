from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0009_drop_fieldnode"),
        ("field", "0004_seed_default_field_devices"),
    ]

    operations = [
        migrations.DeleteModel(name="FieldAgentHeartbeat"),
        migrations.DeleteModel(name="FieldNode"),
        migrations.DeleteModel(name="FieldTag"),
        migrations.DeleteModel(name="FieldDevice"),
        migrations.DeleteModel(name="FieldEndpoint"),
    ]
