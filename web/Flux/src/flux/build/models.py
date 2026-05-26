from __future__ import annotations

from django.db import models


class BuildRun(models.Model):
    class Target(models.TextChoices):
        IGNITION_TAGS = "ignition_tags", "Ignition Tags"
        HMI_SYMBOLIC_MAP = "hmi_symbolic_map", "HMI Symbolic Map"
        LOGIX_L5X = "logix_l5x", "Logix L5X"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    mine_run = models.ForeignKey("mine.MineRun", on_delete=models.PROTECT, related_name="build_runs")
    target = models.CharField(max_length=80, choices=Target.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    output_path = models.CharField(max_length=1200, blank=True)
    output_sha256 = models.CharField(max_length=64, blank=True)
    output_bytes = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["target", "status"], name="build_run_target_status_idx")]

    def __str__(self) -> str:
        return f"{self.target} from mine run {self.mine_run_id}"


class BuildArtifact(models.Model):
    run = models.ForeignKey(BuildRun, on_delete=models.CASCADE, related_name="artifacts")
    kind = models.CharField(max_length=80)
    path = models.CharField(max_length=1200)
    sha256 = models.CharField(max_length=64)
    size_bytes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["run", "kind", "path"]

    def __str__(self) -> str:
        return self.path


class BuildDiagnostic(models.Model):
    run = models.ForeignKey(BuildRun, on_delete=models.CASCADE, related_name="diagnostics")
    severity = models.CharField(max_length=40)
    code = models.CharField(max_length=120)
    message = models.TextField()
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["run", "severity", "code", "id"]
        indexes = [models.Index(fields=["run", "severity"], name="build_diag_severity_idx")]


class HmiMapSelection(models.Model):
    mine_run = models.ForeignKey("mine.MineRun", on_delete=models.CASCADE, related_name="hmi_map_selections")
    screen = models.ForeignKey("mine.HmiScreenFact", on_delete=models.CASCADE, related_name="hmi_map_selections")
    component = models.ForeignKey(
        "mine.HmiComponentFact",
        on_delete=models.CASCADE,
        related_name="hmi_map_selections",
        blank=True,
        null=True,
    )
    enabled = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["mine_run", "screen", "component"], name="unique_hmi_map_selection")
        ]
        indexes = [models.Index(fields=["mine_run", "enabled"], name="hmi_map_sel_run_enabled_idx")]
