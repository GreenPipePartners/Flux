from django.db import migrations


FORWARD_SQL = """
CREATE SCHEMA IF NOT EXISTS "cell";

ALTER TABLE IF EXISTS "public"."cell_cellbundle" SET SCHEMA "cell";
ALTER TABLE IF EXISTS "cell"."cell_cellbundle" RENAME TO "bundle";

ALTER TABLE IF EXISTS "public"."cell_draftcell" SET SCHEMA "cell";
ALTER TABLE IF EXISTS "cell"."cell_draftcell" RENAME TO "cell";

ALTER TABLE IF EXISTS "public"."cell_draftcellpoint" SET SCHEMA "cell";
ALTER TABLE IF EXISTS "cell"."cell_draftcellpoint" RENAME TO "point";

ALTER TABLE IF EXISTS "public"."cell_draftcellrelationship" SET SCHEMA "cell";
ALTER TABLE IF EXISTS "cell"."cell_draftcellrelationship" RENAME TO "relationship";

ALTER TABLE IF EXISTS "public"."cell_draftcellsource" SET SCHEMA "cell";
ALTER TABLE IF EXISTS "cell"."cell_draftcellsource" RENAME TO "source";

ALTER TABLE IF EXISTS "public"."cell_draftcellvisual" SET SCHEMA "cell";
ALTER TABLE IF EXISTS "cell"."cell_draftcellvisual" RENAME TO "visual";

ALTER TABLE IF EXISTS "public"."cell_draftcellcomment" SET SCHEMA "cell";
ALTER TABLE IF EXISTS "cell"."cell_draftcellcomment" RENAME TO "comment";
"""


REVERSE_SQL = """
ALTER TABLE IF EXISTS "cell"."comment" RENAME TO "cell_draftcellcomment";
ALTER TABLE IF EXISTS "cell"."cell_draftcellcomment" SET SCHEMA "public";

ALTER TABLE IF EXISTS "cell"."visual" RENAME TO "cell_draftcellvisual";
ALTER TABLE IF EXISTS "cell"."cell_draftcellvisual" SET SCHEMA "public";

ALTER TABLE IF EXISTS "cell"."source" RENAME TO "cell_draftcellsource";
ALTER TABLE IF EXISTS "cell"."cell_draftcellsource" SET SCHEMA "public";

ALTER TABLE IF EXISTS "cell"."relationship" RENAME TO "cell_draftcellrelationship";
ALTER TABLE IF EXISTS "cell"."cell_draftcellrelationship" SET SCHEMA "public";

ALTER TABLE IF EXISTS "cell"."point" RENAME TO "cell_draftcellpoint";
ALTER TABLE IF EXISTS "cell"."cell_draftcellpoint" SET SCHEMA "public";

ALTER TABLE IF EXISTS "cell"."cell" RENAME TO "cell_draftcell";
ALTER TABLE IF EXISTS "cell"."cell_draftcell" SET SCHEMA "public";

ALTER TABLE IF EXISTS "cell"."bundle" RENAME TO "cell_cellbundle";
ALTER TABLE IF EXISTS "cell"."cell_cellbundle" SET SCHEMA "public";
"""


class Migration(migrations.Migration):
    dependencies = [
        ("cell", "0004_draftcellcomment"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)],
            state_operations=[
                migrations.RenameModel(old_name="CellBundle", new_name="Bundle"),
                migrations.RenameModel(old_name="DraftCell", new_name="Cell"),
                migrations.RenameModel(old_name="DraftCellPoint", new_name="Point"),
                migrations.RenameModel(old_name="DraftCellRelationship", new_name="Relationship"),
                migrations.RenameModel(old_name="DraftCellSource", new_name="Source"),
                migrations.RenameModel(old_name="DraftCellVisual", new_name="Visual"),
                migrations.RenameModel(old_name="DraftCellComment", new_name="Comment"),
                migrations.AlterModelTable(name="bundle", table='"cell"."bundle"'),
                migrations.AlterModelTable(name="cell", table='"cell"."cell"'),
                migrations.AlterModelTable(name="point", table='"cell"."point"'),
                migrations.AlterModelTable(name="relationship", table='"cell"."relationship"'),
                migrations.AlterModelTable(name="source", table='"cell"."source"'),
                migrations.AlterModelTable(name="visual", table='"cell"."visual"'),
                migrations.AlterModelTable(name="comment", table='"cell"."comment"'),
            ],
        ),
    ]
