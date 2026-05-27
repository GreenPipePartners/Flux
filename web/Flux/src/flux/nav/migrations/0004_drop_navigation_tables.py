from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nav", "0003_preserve_well_profile_site"),
    ]

    operations = [
        migrations.DeleteModel(name="NavigationPlacement"),
        migrations.DeleteModel(name="NavigationProfileAction"),
        migrations.DeleteModel(name="NavigationProfileNavOrder"),
        migrations.DeleteModel(name="NavigationProfileOrder"),
        migrations.DeleteModel(name="NavigationStaticOption"),
        migrations.DeleteModel(name="NavigationDimension"),
        migrations.DeleteModel(name="NavigationProfile"),
    ]
