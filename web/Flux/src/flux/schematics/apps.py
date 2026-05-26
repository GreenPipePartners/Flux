from django.apps import AppConfig


class SchematicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "flux.schematics"
    label = "schematics"
    verbose_name = "Flux Schematics"
