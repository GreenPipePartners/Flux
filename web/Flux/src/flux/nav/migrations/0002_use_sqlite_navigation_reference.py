from django.db import migrations


def use_sqlite_navigation_queries(apps, schema_editor):
    dimension_model = apps.get_model("nav", "NavigationDimension")
    for key in ("route", "subroute", "site", "facility", "lease", "well"):
        dimension_model.objects.filter(key=key).update(query_key=f"sqlite.{key}")


class Migration(migrations.Migration):

    dependencies = [
        ("nav", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(use_sqlite_navigation_queries, migrations.RunPython.noop),
    ]
