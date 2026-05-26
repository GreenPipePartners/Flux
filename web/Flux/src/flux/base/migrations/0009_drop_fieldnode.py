from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0008_tagselection_config"),
    ]

    operations = [
        migrations.DeleteModel(name="FieldNode"),
    ]
