from django.apps import AppConfig


class FieldConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "flux.field"
    verbose_name = "Flux Field (legacy migrations)"
