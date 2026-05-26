from django.db import migrations


TABLES = (
    ("mine_minerun", "run"),
    ("mine_plccontrollerfact", "plc_controller"),
    ("mine_plcdatatypefact", "plc_data_type"),
    ("mine_plcmemberfact", "plc_member"),
    ("mine_plctagfact", "plc_tag"),
    ("mine_hmiscreenfact", "hmi_screen"),
    ("mine_hmicomponentfact", "hmi_component"),
    ("mine_hmitagreferencefact", "hmi_tag_reference"),
    ("mine_hmiparameterfilefact", "hmi_parameter_file"),
    ("mine_hmiparameterfact", "hmi_parameter"),
    ("mine_hmicomponentactionfact", "hmi_component_action"),
    ("mine_hmicomponentparameterfact", "hmi_component_parameter"),
    ("mine_hmicomponentstatefact", "hmi_component_state"),
    ("mine_hmiglobalobjectlinkfact", "hmi_global_object_link"),
    ("mine_hmivbalinkfact", "hmi_vba_link"),
)


def quote_identifier(value: str) -> str:
    return '"%s"' % value.replace('"', '""')


def relation(schema: str, table: str) -> str:
    return "%s.%s" % (quote_identifier(schema), quote_identifier(table))


FORWARD_SQL = "\n".join(
    [
        'CREATE SCHEMA IF NOT EXISTS "mine";',
        *(
            "\n".join(
                [
                    "ALTER TABLE %s SET SCHEMA %s;" % (relation("public", old_table), quote_identifier("mine")),
                    "ALTER TABLE %s RENAME TO %s;" % (relation("mine", old_table), quote_identifier(new_table)),
                ]
            )
            for old_table, new_table in TABLES
        ),
    ]
)


REVERSE_SQL = "\n".join(
    "\n".join(
        [
            "ALTER TABLE %s RENAME TO %s;" % (relation("mine", new_table), quote_identifier(old_table)),
            "ALTER TABLE %s SET SCHEMA %s;" % (relation("mine", old_table), quote_identifier("public")),
        ]
    )
    for old_table, new_table in reversed(TABLES)
)


def verify_mine_schema_tables(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    target_tables = {new_table for _, new_table in TABLES}
    old_tables = {old_table for old_table, _ in TABLES}

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = %s
            """,
            ["mine"],
        )
        mine_tables = {row[0] for row in cursor.fetchall()}

        cursor.execute(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = %s
            """,
            ["public"],
        )
        public_tables = {row[0] for row in cursor.fetchall()}

    missing = sorted(target_tables - mine_tables)
    remaining_old = sorted(old_tables & public_tables)
    if missing or remaining_old:
        raise RuntimeError(
            "Flux.mine schema migration postcondition failed: "
            "missing target tables=%s; remaining public tables=%s"
            % (missing, remaining_old)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("mine", "0002_hmicomponentactionfact_hmicomponentparameterfact_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)],
            state_operations=[
                migrations.AlterModelTable(name="minerun", table='"mine"."run"'),
                migrations.AlterModelTable(name="plccontrollerfact", table='"mine"."plc_controller"'),
                migrations.AlterModelTable(name="plcdatatypefact", table='"mine"."plc_data_type"'),
                migrations.AlterModelTable(name="plcmemberfact", table='"mine"."plc_member"'),
                migrations.AlterModelTable(name="plctagfact", table='"mine"."plc_tag"'),
                migrations.AlterModelTable(name="hmiscreenfact", table='"mine"."hmi_screen"'),
                migrations.AlterModelTable(name="hmicomponentfact", table='"mine"."hmi_component"'),
                migrations.AlterModelTable(name="hmitagreferencefact", table='"mine"."hmi_tag_reference"'),
                migrations.AlterModelTable(name="hmiparameterfilefact", table='"mine"."hmi_parameter_file"'),
                migrations.AlterModelTable(name="hmiparameterfact", table='"mine"."hmi_parameter"'),
                migrations.AlterModelTable(name="hmicomponentactionfact", table='"mine"."hmi_component_action"'),
                migrations.AlterModelTable(name="hmicomponentparameterfact", table='"mine"."hmi_component_parameter"'),
                migrations.AlterModelTable(name="hmicomponentstatefact", table='"mine"."hmi_component_state"'),
                migrations.AlterModelTable(name="hmiglobalobjectlinkfact", table='"mine"."hmi_global_object_link"'),
                migrations.AlterModelTable(name="hmivbalinkfact", table='"mine"."hmi_vba_link"'),
            ],
        ),
        migrations.RunPython(verify_mine_schema_tables, migrations.RunPython.noop),
    ]
