import django.db.models.deletion
from django.db import migrations, models


DIMENSIONS = [
    ("field", "Field"),
    ("route", "Route"),
    ("subroute", "Subroute"),
    ("site", "Pad"),
    ("facility", "Facility"),
    ("lease", "Lease"),
    ("well", "Well"),
]

PROFILES = {
    "route": {
        "label": "Route Navigation",
        "order": ["route"],
        "nav_order": ["route"],
        "actions": [(1, "route", False, "normal", True)],
    },
    "site": {
        "label": "Pad Navigation",
        "order": ["route", "subroute", "site"],
        "nav_order": ["subroute", "site"],
        "actions": [
            (1, "route", False, "normal", True),
            (2, "subroute", False, "normal", True),
            (3, "site", False, "upstream", True),
        ],
    },
    "well": {
        "label": "Well Navigation",
        "order": ["route", "subroute", "site", "well"],
        "nav_order": ["subroute", "site", "well"],
        "actions": [
            (1, "route", False, "normal", True),
            (2, "subroute", False, "normal", True),
            (3, "site", False, "upstream", True),
            (4, "well", False, "upstream", True),
            (5, "lease", False, "normal", False),
            (6, "facility", True, "none", False),
        ],
    },
    "facility": {
        "label": "Facility Navigation",
        "order": ["facility"],
        "nav_order": ["facility"],
        "actions": [(1, "facility", False, "normal", False)],
    },
    "lease": {
        "label": "Lease Navigation",
        "order": ["facility", "lease"],
        "nav_order": ["facility", "lease"],
        "actions": [
            (1, "facility", False, "normal", True),
            (2, "lease", False, "normal", False),
        ],
    },
}

OPTIONS = {
    "field": [("1", "Pinedale")],
    "route": [("1", "PD-1N"), ("2", "PD-2NC"), ("3", "PD-3SC"), ("4", "PD-4S")],
    "subroute": [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")],
    "site": [("1", "Demo Pad 01"), ("2", "Demo Pad 02")],
    "facility": [("1", "Demo Facility 01"), ("2", "Demo Facility 02")],
    "lease": [("1", "Demo Lease 01"), ("2", "Demo Lease 02")],
    "well": [("1", "DemoWell_01"), ("2", "DemoWell_02")],
}


def seed_navigation(apps, schema_editor):
    dimension_model = apps.get_model("nav", "NavigationDimension")
    profile_model = apps.get_model("nav", "NavigationProfile")
    order_model = apps.get_model("nav", "NavigationProfileOrder")
    nav_order_model = apps.get_model("nav", "NavigationProfileNavOrder")
    action_model = apps.get_model("nav", "NavigationProfileAction")
    placement_model = apps.get_model("nav", "NavigationPlacement")
    option_model = apps.get_model("nav", "NavigationStaticOption")

    dimensions = {}
    for key, label in DIMENSIONS:
        dimensions[key], _created = dimension_model.objects.update_or_create(
            key=key,
            defaults={"label": label, "query_key": f"static.{key}", "enabled": True},
        )
    for key, options in OPTIONS.items():
        for index, (value, label) in enumerate(options, start=1):
            option_model.objects.update_or_create(
                dimension=dimensions[key],
                value=value,
                defaults={"label": label, "sort_order": index, "enabled": True},
            )
    for key, config in PROFILES.items():
        profile, _created = profile_model.objects.update_or_create(
            key=key,
            defaults={"label": config["label"], "enabled": True},
        )
        order_model.objects.filter(profile=profile).delete()
        nav_order_model.objects.filter(profile=profile).delete()
        action_model.objects.filter(profile=profile).delete()
        for position, dimension_key in enumerate(config["order"], start=1):
            order_model.objects.create(profile=profile, dimension=dimensions[dimension_key], position=position)
        for position, dimension_key in enumerate(config["nav_order"], start=1):
            nav_order_model.objects.create(profile=profile, dimension=dimensions[dimension_key], position=position)
        for step, dimension_key, clear, filter_mode, define in config["actions"]:
            action_model.objects.create(
                profile=profile,
                step=step,
                dimension=dimensions[dimension_key],
                clear=clear,
                filter_mode=filter_mode,
                define=define,
            )
    placement_model.objects.update_or_create(
        view_key="live.pad_overview",
        profile=profile_model.objects.get(key="well"),
        defaults={"enabled": True},
    )


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="NavigationDimension",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=80, unique=True)),
                ("label", models.CharField(max_length=120)),
                ("query_key", models.CharField(max_length=120)),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={"ordering": ["key"]},
        ),
        migrations.CreateModel(
            name="NavigationProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=80, unique=True)),
                ("label", models.CharField(max_length=120)),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={"ordering": ["key"]},
        ),
        migrations.CreateModel(
            name="NavigationPlacement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("view_key", models.CharField(max_length=120)),
                ("enabled", models.BooleanField(default=True)),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="placements", to="nav.navigationprofile")),
            ],
            options={"ordering": ["view_key", "profile__key"]},
        ),
        migrations.CreateModel(
            name="NavigationProfileAction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("step", models.PositiveSmallIntegerField()),
                ("clear", models.BooleanField(default=False)),
                ("filter_mode", models.CharField(choices=[("none", "None"), ("normal", "Normal"), ("upstream", "Upstream")], default="none", max_length=20)),
                ("define", models.BooleanField(default=False)),
                ("dimension", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="nav.navigationdimension")),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="actions", to="nav.navigationprofile")),
            ],
            options={"ordering": ["profile__key", "step"]},
        ),
        migrations.CreateModel(
            name="NavigationProfileNavOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveSmallIntegerField()),
                ("dimension", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="nav.navigationdimension")),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="nav_order", to="nav.navigationprofile")),
            ],
            options={"ordering": ["profile__key", "position"]},
        ),
        migrations.CreateModel(
            name="NavigationProfileOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveSmallIntegerField()),
                ("dimension", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="nav.navigationdimension")),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="filter_order", to="nav.navigationprofile")),
            ],
            options={"ordering": ["profile__key", "position"]},
        ),
        migrations.CreateModel(
            name="NavigationStaticOption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("value", models.CharField(max_length=120)),
                ("label", models.CharField(max_length=255)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("enabled", models.BooleanField(default=True)),
                ("dimension", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="static_options", to="nav.navigationdimension")),
            ],
            options={"ordering": ["dimension__key", "sort_order", "label"]},
        ),
        migrations.AddConstraint(model_name="navigationplacement", constraint=models.UniqueConstraint(fields=("view_key", "profile"), name="unique_nav_profile_placement")),
        migrations.AddConstraint(model_name="navigationprofileaction", constraint=models.UniqueConstraint(fields=("profile", "step"), name="unique_nav_profile_action_step")),
        migrations.AddConstraint(model_name="navigationprofilenavorder", constraint=models.UniqueConstraint(fields=("profile", "position"), name="unique_nav_traversal_order")),
        migrations.AddConstraint(model_name="navigationprofileorder", constraint=models.UniqueConstraint(fields=("profile", "position"), name="unique_nav_filter_order")),
        migrations.AddConstraint(model_name="navigationstaticoption", constraint=models.UniqueConstraint(fields=("dimension", "value"), name="unique_nav_static_option")),
        migrations.RunPython(seed_navigation, migrations.RunPython.noop),
    ]
