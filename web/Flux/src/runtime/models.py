from django.db import models
from django.utils import timezone


class TagSchedule(models.Model):
    name = models.CharField(max_length=80, unique=True)
    interval_seconds = models.PositiveIntegerField(default=30)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["interval_seconds", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.interval_seconds}s)"


class RuntimeTag(models.Model):
    provider = models.CharField(max_length=120)
    path = models.CharField(max_length=1000)
    display_name = models.CharField(max_length=255)
    asset_name = models.CharField(max_length=255, blank=True)
    engineering_units = models.CharField(max_length=40, blank=True)
    schedule = models.ForeignKey(TagSchedule, on_delete=models.PROTECT, related_name="tags")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "path"], name="unique_runtime_tag_path")
        ]
        ordering = ["asset_name", "display_name"]

    @property
    def full_path(self) -> str:
        return f"[{self.provider}]{self.path}"

    def __str__(self) -> str:
        return self.display_name


class LatestTagValue(models.Model):
    tag = models.OneToOneField(RuntimeTag, on_delete=models.CASCADE, related_name="latest_value")
    value = models.JSONField(blank=True, null=True)
    quality_code = models.CharField(max_length=120, default="Good")
    value_timestamp = models.DateTimeField()
    read_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tag__asset_name", "tag__display_name"]

    def is_stale(self, now=None, stale_after_seconds=120) -> bool:
        now = now or timezone.now()
        return (now - self.read_at).total_seconds() > stale_after_seconds

    def __str__(self) -> str:
        return f"{self.tag}: {self.value}"


class TagSample(models.Model):
    tag = models.ForeignKey(RuntimeTag, on_delete=models.CASCADE, related_name="samples")
    value = models.JSONField(blank=True, null=True)
    quality_code = models.CharField(max_length=120, default="Good")
    value_timestamp = models.DateTimeField()
    read_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [models.Index(fields=["tag", "-read_at"])]
        ordering = ["-read_at"]

    def __str__(self) -> str:
        return f"{self.tag} sample at {self.read_at}"
