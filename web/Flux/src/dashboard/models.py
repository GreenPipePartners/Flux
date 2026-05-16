from django.db import models


class IgnitionBridgeConfig(models.Model):
    name = models.CharField(max_length=64, unique=True, default="default")
    base_url = models.URLField(default="http://localhost:8088/system/webdev/flux")
    token = models.CharField(max_length=255, blank=True)
    last_test_ok = models.BooleanField(default=False)
    last_test_message = models.CharField(max_length=255, blank=True)
    last_test_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ignition bridge config"
        verbose_name_plural = "Ignition bridge config"

    def __str__(self):
        return self.name
