from django.db import migrations


def preserve_site_in_well_profile(apps, schema_editor):
    action_model = apps.get_model("nav", "NavigationProfileAction")
    action_model.objects.filter(profile__key="well", dimension__key="site").update(clear=False)


class Migration(migrations.Migration):

    dependencies = [
        ("nav", "0002_use_sqlite_navigation_reference"),
    ]

    operations = [
        migrations.RunPython(preserve_site_in_well_profile, migrations.RunPython.noop),
    ]
