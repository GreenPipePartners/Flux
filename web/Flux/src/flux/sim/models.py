from django.db import models


class SimProviderSelection(models.Model):
    provider = models.CharField(max_length=120)
    path = models.CharField(max_length=1200)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "path"], name="unique_sim_provider_selection")]
        ordering = ["provider", "path"]

    def __str__(self) -> str:
        return f"{self.provider}:{self.path}"
