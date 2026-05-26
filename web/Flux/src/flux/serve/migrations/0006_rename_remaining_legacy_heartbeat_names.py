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
        WHERE n.nspname = 'serve'
    LOOP
        new_name := replace(item.object_name, 'base_fieldagentheartbeat', 'serve_sim_agent_heartbeat');
        IF new_name <> item.object_name THEN
            EXECUTE format('ALTER TABLE %I.%I RENAME CONSTRAINT %I TO %I', item.schema_name, item.table_name, item.object_name, new_name);
        END IF;
    END LOOP;

    FOR item IN
        SELECT schemaname AS schema_name, indexname AS object_name
        FROM pg_indexes
        WHERE schemaname = 'serve'
    LOOP
        new_name := replace(item.object_name, 'base_fieldagentheartbeat', 'serve_sim_agent_heartbeat');
        IF new_name <> item.object_name THEN
            EXECUTE format('ALTER INDEX %I.%I RENAME TO %I', item.schema_name, item.object_name, new_name);
        END IF;
    END LOOP;
END $$;
"""


REVERSE_SQL = migrations.RunSQL.noop


class Migration(migrations.Migration):
    dependencies = [("serve", "0005_rename_sim_agent_heartbeat_constraint")]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
