from django.db import models
from django.utils import timezone


class SimSchedule(models.Model):
    name = models.CharField(max_length=80, unique=True)
    interval_seconds = models.PositiveIntegerField(default=5)
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["interval_seconds", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.interval_seconds}s)"


class SimTag(models.Model):
    class DataType(models.TextChoices):
        BOOLEAN = "Boolean", "Boolean"
        INT4 = "Int4", "Integer"
        FLOAT8 = "Float8", "Float"

    class Pattern(models.TextChoices):
        BOOL_TOGGLE = "bool_toggle", "Boolean toggle"
        INT_RAMP = "int_ramp", "Integer ramp"
        FLOAT_WAVE = "float_wave", "Float wave"

    provider = models.CharField(max_length=120, default="default")
    folder_path = models.CharField(max_length=1000, default="FluxSim")
    name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    data_type = models.CharField(max_length=20, choices=DataType.choices)
    pattern = models.CharField(max_length=40, choices=Pattern.choices)
    schedule = models.ForeignKey(SimSchedule, on_delete=models.PROTECT, related_name="tags")
    enabled = models.BooleanField(default=True)
    baseline = models.FloatField(default=0.0)
    amplitude = models.FloatField(default=1.0)
    step = models.FloatField(default=1.0)
    period_samples = models.PositiveIntegerField(default=10)
    history_enabled = models.BooleanField(default=True)
    last_value = models.JSONField(blank=True, null=True)
    last_write_at = models.DateTimeField(blank=True, null=True)
    next_write_at = models.DateTimeField(default=timezone.now, db_index=True)
    sample_index = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "folder_path", "name"], name="unique_sim_tag_path")]
        ordering = ["provider", "folder_path", "name"]

    @property
    def tag_path(self) -> str:
        return f"[{self.provider}]{self.folder_path.strip('/')}/{self.name}"

    @property
    def label(self) -> str:
        return self.display_name or self.name

    def __str__(self) -> str:
        return self.tag_path


class SimHistoryBackfill(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    name = models.CharField(max_length=120, unique=True)
    history_prefix = models.CharField(max_length=1200)
    start_at = models.DateTimeField()
    duration_days = models.PositiveIntegerField(default=365)
    interval_seconds = models.PositiveIntegerField(default=3600)
    chunk_size = models.PositiveIntegerField(default=5000)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


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
