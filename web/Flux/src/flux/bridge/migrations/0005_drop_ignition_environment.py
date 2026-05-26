from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("bridge", "0004_move_ignition_environment_to_bridge_schema"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="DROP TABLE IF EXISTS bridge.ignition_environment;",
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.DeleteModel(name="IgnitionEnvironment"),
            ],
        ),
    ]
