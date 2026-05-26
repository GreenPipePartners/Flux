import re

from django.db import models


class IgnitionBridgeConfig(models.Model):
    class Role(models.TextChoices):
        PRODUCTION = "production", "Production"
        SIMULATOR = "simulator", "Simulator"

    name = models.CharField(max_length=64, unique=True, default="default")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SIMULATOR)
    base_url = models.URLField(default="http://localhost:8088/system/webdev/flux")
    token = models.CharField(max_length=255, blank=True)
    last_test_ok = models.BooleanField(default=False)
    last_test_message = models.CharField(max_length=255, blank=True)
    last_test_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"bridge"."ignition_bridge"'
        verbose_name = "Ignition bridge config"
        verbose_name_plural = "Ignition bridge config"

    def __str__(self):
        return self.name

    @property
    def status_label(self) -> str:
        if self.last_test_ok:
            return "connected"
        if self.last_test_at:
            return "failed"
        return "untested"

    @property
    def last_test_summary(self) -> str:
        if not self.last_test_message:
            return ""
        http_match = re.search(r"HTTP (\d+)", self.last_test_message)
        json_match = re.search(r'"message"\s*:\s*"([^"]+)"', self.last_test_message)
        if http_match and json_match:
            return "HTTP %s: %s" % (http_match.group(1), json_match.group(1))
        return self.last_test_message.splitlines()[0][:96]

