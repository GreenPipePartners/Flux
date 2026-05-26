from django.db import migrations


FORWARD_SQL = r"""
DO $$
DECLARE
    item record;
    new_name text;
BEGIN
    FOR item IN
        SELECT n.nspname AS schema_name, c.relname AS table_name, con.conname AS object_name
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'sim'
    LOOP
        new_name := item.object_name;
        new_name := replace(new_name, 'base_tagnode', 'sim_provider_node');
        new_name := replace(new_name, 'base_tagprovider', 'sim_provider');
        new_name := replace(new_name, 'base_tagselection', 'sim_provider_selection');
        new_name := replace(new_name, 'base_simserver', 'sim_server');
        new_name := replace(new_name, 'base_simdriver', 'sim_driver');
        new_name := replace(new_name, 'base_fieldendpoint', 'sim_endpoint');
        IF new_name <> item.object_name THEN
            EXECUTE format('ALTER TABLE %I.%I RENAME CONSTRAINT %I TO %I', item.schema_name, item.table_name, item.object_name, new_name);
        END IF;
    END LOOP;

    FOR item IN
        SELECT schemaname AS schema_name, indexname AS object_name
        FROM pg_indexes
        WHERE schemaname = 'sim'
    LOOP
        new_name := item.object_name;
        new_name := replace(new_name, 'base_tagnode', 'sim_provider_node');
        new_name := replace(new_name, 'base_tagprovider', 'sim_provider');
        new_name := replace(new_name, 'base_tagselection', 'sim_provider_selection');
        new_name := replace(new_name, 'base_simserver', 'sim_server');
        new_name := replace(new_name, 'base_simdriver', 'sim_driver');
        new_name := replace(new_name, 'base_fieldendpoint', 'sim_endpoint');
        IF new_name <> item.object_name THEN
            EXECUTE format('ALTER INDEX %I.%I RENAME TO %I', item.schema_name, item.object_name, new_name);
        END IF;
    END LOOP;
END $$;
"""


REVERSE_SQL = migrations.RunSQL.noop


class Migration(migrations.Migration):
    dependencies = [
        ("sim", "0017_rename_legacy_catalog_constraints"),
    ]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
