from django.apps import AppConfig


class StatusConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "flux.status"
    label = "status"
    verbose_name = "Flux Status"
