from django.conf import settings
from django.db import models
from django.utils import timezone


class ServeHeartbeat(models.Model):
    class Status(models.TextChoices):
        STARTING = "starting", "Starting"
        RUNNING = "running", "Running"
        PAUSED = "paused", "Paused"
        STOPPED = "stopped", "Stopped"
        ERROR = "error", "Error"

    class Platform(models.TextChoices):
        LINUX = "linux", "Linux"
        UNKNOWN = "unknown", "Unknown"

    service_name = models.CharField(max_length=120)
    instance_id = models.CharField(max_length=120)
    platform = models.CharField(max_length=20, choices=Platform.choices, default=Platform.UNKNOWN)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STARTING)
    pid = models.PositiveIntegerField(blank=True, null=True)
    version = models.CharField(max_length=80, blank=True)
    started_at = models.DateTimeField(blank=True, null=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    current_job = models.CharField(max_length=255, blank=True)
    last_error = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["service_name", "instance_id"], name="unique_serve_heartbeat_instance"
            )
        ]
        ordering = ["service_name", "instance_id"]

    def __str__(self) -> str:
        return f"{self.service_name} ({self.instance_id})"


class ServeServiceSnapshot(models.Model):
    class DesiredState(models.TextChoices):
        REQUIRED = "required", "Required"
        EXPECTED = "expected", "Expected"
        OPTIONAL = "optional", "Optional"
        EXTERNAL = "external", "External"
        DISABLED = "disabled", "Disabled"

    class ObservedState(models.TextChoices):
        HEALTHY = "healthy", "Healthy"
        DEGRADED = "degraded", "Degraded"
        MISSING = "missing", "Missing"
        STALE = "stale", "Stale"
        ERROR = "error", "Error"
        UNKNOWN = "unknown", "Unknown"
        STOPPED = "stopped", "Stopped"

    class Severity(models.TextChoices):
        OK = "ok", "OK"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        UNKNOWN = "unknown", "Unknown"

    service_key = models.CharField(max_length=180, unique=True)
    display_name = models.CharField(max_length=180)
    category = models.CharField(max_length=80)
    desired_state = models.CharField(max_length=20, choices=DesiredState.choices, default=DesiredState.EXPECTED)
    observed_state = models.CharField(max_length=20, choices=ObservedState.choices, default=ObservedState.UNKNOWN)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.UNKNOWN)
    last_checked_at = models.DateTimeField(default=timezone.now, db_index=True)
    summary = models.CharField(max_length=255, blank=True)
    detail = models.TextField(blank=True)
    last_error = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "service_key"]

    def __str__(self) -> str:
        return f"{self.service_key}: {self.observed_state}"


class ServeCommand(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        CLAIMED = "claimed", "Claimed"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    command = models.CharField(max_length=80)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="serve_commands",
    )
    requested_at = models.DateTimeField(default=timezone.now, db_index=True)
    claimed_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self) -> str:
        return f"{self.command} ({self.status})"


class SimAgentHeartbeat(models.Model):
    endpoint = models.ForeignKey("sim.Endpoint", on_delete=models.CASCADE, related_name="heartbeats")
    instance_id = models.CharField(max_length=120)
    process_id = models.PositiveIntegerField(blank=True, null=True)
    version = models.CharField(max_length=80, blank=True)
    started_at = models.DateTimeField(blank=True, null=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    current_node_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        db_table = '"serve"."sim_agent_heartbeat"'
        constraints = [
            models.UniqueConstraint(fields=["endpoint", "instance_id"], name="unique_serve_sim_agent_instance")
        ]
        ordering = ["endpoint", "instance_id"]

    def __str__(self) -> str:
        return f"{self.endpoint} ({self.instance_id})"


FieldAgentHeartbeat = SimAgentHeartbeat
