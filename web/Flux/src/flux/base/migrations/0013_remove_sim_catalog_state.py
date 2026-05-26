from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0012_entity"),
        ("sim", "0014_provider_catalog_schema"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="TagSelection"),
                migrations.DeleteModel(name="TagNode"),
                migrations.DeleteModel(name="TagProvider"),
                migrations.DeleteModel(name="SimServer"),
                migrations.DeleteModel(name="SimDriver"),
            ],
        ),
    ]
