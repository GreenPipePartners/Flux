from django.apps import AppConfig


class SimConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "flux.sim"
    verbose_name = "Flux Sim"
