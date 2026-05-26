import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mine", "0003_mine_schema_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlcProgramFact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("main_routine_name", models.CharField(blank=True, max_length=255)),
                ("raw", models.JSONField(blank=True, default=dict)),
                (
                    "controller",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="programs", to="mine.plccontrollerfact"),
                ),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="plc_programs", to="mine.minerun")),
            ],
            options={
                "db_table": '"mine"."plc_program"',
                "ordering": ["controller", "name"],
            },
        ),
        migrations.CreateModel(
            name="PlcTaskFact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("task_type", models.CharField(blank=True, max_length=80)),
                ("priority", models.IntegerField(blank=True, null=True)),
                ("rate", models.IntegerField(blank=True, null=True)),
                ("watchdog", models.IntegerField(blank=True, null=True)),
                ("disable_update_outputs", models.BooleanField(blank=True, null=True)),
                ("inhibit_task", models.BooleanField(blank=True, null=True)),
                ("raw", models.JSONField(blank=True, default=dict)),
                (
                    "controller",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to="mine.plccontrollerfact"),
                ),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="plc_tasks", to="mine.minerun")),
            ],
            options={
                "db_table": '"mine"."plc_task"',
                "ordering": ["controller", "name"],
            },
        ),
        migrations.CreateModel(
            name="PlcRoutineFact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("routine_type", models.CharField(blank=True, max_length=80)),
                ("raw", models.JSONField(blank=True, default=dict)),
                (
                    "program",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="routines", to="mine.plcprogramfact"),
                ),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="plc_routines", to="mine.minerun")),
            ],
            options={
                "db_table": '"mine"."plc_routine"',
                "ordering": ["program", "name"],
            },
        ),
        migrations.CreateModel(
            name="PlcScheduledProgramFact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                (
                    "program",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scheduled_task_links",
                        to="mine.plcprogramfact",
                    ),
                ),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="plc_scheduled_programs", to="mine.minerun")),
                (
                    "task",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scheduled_programs", to="mine.plctaskfact"),
                ),
            ],
            options={
                "db_table": '"mine"."plc_scheduled_program"',
                "ordering": ["task", "sort_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="PlcRungFact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.PositiveIntegerField()),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("rung_type", models.CharField(blank=True, max_length=80)),
                ("text", models.TextField(blank=True)),
                ("comment", models.TextField(blank=True)),
                ("raw", models.JSONField(blank=True, default=dict)),
                (
                    "routine",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rungs", to="mine.plcroutinefact"),
                ),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="plc_rungs", to="mine.minerun")),
            ],
            options={
                "db_table": '"mine"."plc_rung"',
                "ordering": ["routine", "sort_order", "number"],
            },
        ),
        migrations.AddIndex(
            model_name="plcprogramfact",
            index=models.Index(fields=["run", "name"], name="mine_plc_program_run_idx"),
        ),
        migrations.AddIndex(
            model_name="plctaskfact",
            index=models.Index(fields=["run", "task_type"], name="mine_plc_task_type_idx"),
        ),
        migrations.AddIndex(
            model_name="plcroutinefact",
            index=models.Index(fields=["run", "routine_type"], name="mine_plc_routine_type_idx"),
        ),
        migrations.AddIndex(
            model_name="plcscheduledprogramfact",
            index=models.Index(fields=["run", "name"], name="mine_plc_sched_program_idx"),
        ),
        migrations.AddIndex(
            model_name="plcrungfact",
            index=models.Index(fields=["run", "rung_type"], name="mine_plc_rung_type_idx"),
        ),
        migrations.AddConstraint(
            model_name="plcprogramfact",
            constraint=models.UniqueConstraint(fields=("controller", "name"), name="unique_mine_program_per_controller"),
        ),
        migrations.AddConstraint(
            model_name="plctaskfact",
            constraint=models.UniqueConstraint(fields=("controller", "name"), name="unique_mine_task_per_controller"),
        ),
        migrations.AddConstraint(
            model_name="plcroutinefact",
            constraint=models.UniqueConstraint(fields=("program", "name"), name="unique_mine_routine_per_program"),
        ),
        migrations.AddConstraint(
            model_name="plcscheduledprogramfact",
            constraint=models.UniqueConstraint(fields=("task", "sort_order", "name"), name="unique_mine_task_program_order"),
        ),
        migrations.AddConstraint(
            model_name="plcrungfact",
            constraint=models.UniqueConstraint(fields=("routine", "number"), name="unique_mine_rung_per_routine"),
        ),
    ]
