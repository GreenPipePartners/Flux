from django.apps import AppConfig


class OptConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "flux.opt"
    verbose_name = "Flux Opt"
