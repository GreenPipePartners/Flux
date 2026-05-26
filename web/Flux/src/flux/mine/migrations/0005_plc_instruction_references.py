import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mine", "0004_plc_source_graph"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlcInstructionFact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("mnemonic", models.CharField(max_length=80)),
                ("operands", models.JSONField(blank=True, default=list)),
                ("raw", models.JSONField(blank=True, default=dict)),
                (
                    "run",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="plc_instructions", to="mine.minerun"),
                ),
                (
                    "rung",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="instructions", to="mine.plcrungfact"),
                ),
            ],
            options={
                "db_table": '"mine"."plc_instruction"',
                "ordering": ["rung", "sort_order"],
            },
        ),
        migrations.CreateModel(
            name="PlcTagReferenceFact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scope", models.CharField(default="Global", max_length=255)),
                ("original", models.CharField(max_length=1200)),
                ("base_tag", models.CharField(max_length=255)),
                ("member_path", models.CharField(blank=True, max_length=1200)),
                ("operand_index", models.PositiveIntegerField(default=0)),
                ("role", models.CharField(default="unknown", max_length=80)),
                ("raw", models.JSONField(blank=True, default=dict)),
                (
                    "instruction",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tag_references", to="mine.plcinstructionfact"),
                ),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="plc_tag_references", to="mine.minerun")),
                (
                    "rung",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tag_references", to="mine.plcrungfact"),
                ),
                (
                    "tag",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="plc_references",
                        to="mine.plctagfact",
                    ),
                ),
            ],
            options={
                "db_table": '"mine"."plc_tag_reference"',
                "ordering": ["rung", "instruction", "operand_index", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="plcinstructionfact",
            index=models.Index(fields=["run", "mnemonic"], name="mine_plc_instruction_idx"),
        ),
        migrations.AddIndex(
            model_name="plctagreferencefact",
            index=models.Index(fields=["run", "base_tag"], name="mine_plc_ref_tag_idx"),
        ),
        migrations.AddIndex(
            model_name="plctagreferencefact",
            index=models.Index(fields=["run", "role"], name="mine_plc_ref_role_idx"),
        ),
        migrations.AddIndex(
            model_name="plctagreferencefact",
            index=models.Index(fields=["instruction", "operand_index"], name="mine_plc_ref_operand_idx"),
        ),
        migrations.AddConstraint(
            model_name="plcinstructionfact",
            constraint=models.UniqueConstraint(fields=("rung", "sort_order"), name="unique_mine_instruction_order"),
        ),
    ]
