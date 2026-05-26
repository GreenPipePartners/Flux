from django.db import migrations, models


OPEN_LEASE_INDEX = models.Index(
    fields=["work_type", "target_path"],
    name="opt_open_lease_work_target_idx",
    condition=models.Q(completed_at__isnull=True),
)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("opt", "0003_runtime_demand"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS opt_open_lease_work_target_idx "
                        "ON opt_optimizationlease (work_type, target_path) "
                        "WHERE completed_at IS NULL"
                    ),
                    reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS opt_open_lease_work_target_idx",
                )
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="optimizationlease",
                    index=OPEN_LEASE_INDEX,
                )
            ],
        )
    ]
