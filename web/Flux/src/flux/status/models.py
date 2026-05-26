from django.db import models


class LatestStatus(models.Model):
    class StatusKind(models.TextChoices):
        CONNECTIVITY = "connectivity", "Connectivity"
        SAMPLING = "sampling", "Sampling"
        FRESHNESS = "freshness", "Freshness"
        QUALITY = "quality", "Quality"
        WORKER = "worker", "Worker"
        STORAGE = "storage", "Storage"
        CONFIGURATION = "configuration", "Configuration"

    class ObservedState(models.TextChoices):
        OK = "ok", "OK"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        STALE = "stale", "Stale"
        MISSING = "missing", "Missing"
        UNKNOWN = "unknown", "Unknown"
        DISABLED = "disabled", "Disabled"

    class Severity(models.TextChoices):
        OK = "ok", "OK"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        UNKNOWN = "unknown", "Unknown"

    entity = models.ForeignKey("base.Entity", on_delete=models.CASCADE, related_name="latest_statuses")
    status_kind = models.CharField(max_length=40, choices=StatusKind.choices)
    observed_state = models.CharField(max_length=40, choices=ObservedState.choices, default=ObservedState.UNKNOWN)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.UNKNOWN)
    summary = models.CharField(max_length=255, blank=True)
    detail = models.TextField(blank=True)
    last_seen_at = models.DateTimeField(blank=True, null=True)
    stale_after_seconds = models.PositiveIntegerField(blank=True, null=True)
    source = models.CharField(max_length=120)
    source_instance = models.CharField(max_length=180, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"status"."latest"'
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "status_kind", "source", "source_instance"],
                name="unique_status_latest_entity_kind_source",
            )
        ]
        indexes = [
            models.Index(fields=["entity", "status_kind"], name="status_latest_entity_kind_idx"),
            models.Index(fields=["observed_state"], name="status_latest_observed_idx"),
            models.Index(fields=["severity"], name="status_latest_severity_idx"),
            models.Index(fields=["last_seen_at"], name="status_latest_seen_idx"),
        ]
        ordering = ["entity", "status_kind", "source", "source_instance"]

    def __str__(self) -> str:
        return f"{self.entity}: {self.status_kind}={self.observed_state}"
