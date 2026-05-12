from django.db import models
from django.utils import timezone


class RefreshLane(models.Model):
    name = models.CharField(max_length=40, unique=True)
    interval_seconds = models.PositiveIntegerField(default=30)
    priority = models.PositiveIntegerField(default=100)
    max_batch_size = models.PositiveIntegerField(default=100)
    max_runtime_ms = models.PositiveIntegerField(default=5_000)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "interval_seconds", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.interval_seconds}s)"


class OptimizedTagPath(models.Model):
    provider = models.CharField(max_length=120)
    path = models.CharField(max_length=1000)
    full_path = models.CharField(max_length=1124, unique=True)
    lane = models.ForeignKey(RefreshLane, on_delete=models.PROTECT, related_name="tag_paths")
    enabled = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(blank=True, null=True)
    last_browsed_at = models.DateTimeField(blank=True, null=True)
    last_read_at = models.DateTimeField(blank=True, null=True)
    next_due_at = models.DateTimeField(default=timezone.now, db_index=True)
    failure_count = models.PositiveIntegerField(default=0)
    average_duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["next_due_at", "full_path"]

    def __str__(self) -> str:
        return self.full_path


class BrowseNode(models.Model):
    provider = models.CharField(max_length=120)
    path = models.CharField(max_length=1000)
    parent_path = models.CharField(max_length=1000, blank=True)
    has_children = models.BooleanField(default=False)
    discovered_at = models.DateTimeField(default=timezone.now)
    last_browsed_at = models.DateTimeField(blank=True, null=True)
    next_due_at = models.DateTimeField(default=timezone.now, db_index=True)
    cold_score = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "path"], name="unique_browse_node")]
        ordering = ["provider", "path"]

    def __str__(self) -> str:
        return f"[{self.provider}]{self.path}"


class OptimizationLease(models.Model):
    work_type = models.CharField(max_length=80)
    target_path = models.CharField(max_length=1124)
    claimed_by = models.CharField(max_length=120)
    claimed_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["expires_at", "work_type", "target_path"]

    def __str__(self) -> str:
        return f"{self.work_type}: {self.target_path}"
