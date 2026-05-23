from __future__ import annotations

from django.db import models


class MineRun(models.Model):
    class SourceType(models.TextChoices):
        PLC_L5X = "plc_l5x", "PLC L5X"
        PLC_L5K = "plc_l5k", "PLC L5K"
        FACTORYTALK = "factorytalk", "FactoryTalk"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    label = models.CharField(max_length=240, blank=True)
    source_type = models.CharField(max_length=40, choices=SourceType.choices)
    source_path = models.CharField(max_length=1200)
    source_sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["source_type", "status"], name="mine_run_source_status_idx"),
            models.Index(fields=["source_sha256"], name="mine_run_sha_idx"),
        ]

    def __str__(self) -> str:
        return self.label or self.source_path


class PlcControllerFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="plc_controllers")
    name = models.CharField(max_length=255)
    processor_type = models.CharField(max_length=120, blank=True)
    major_version = models.IntegerField(blank=True, null=True)
    comm_path = models.CharField(max_length=1200, blank=True)
    data_type_count = models.PositiveIntegerField(default=0)
    global_tag_count = models.PositiveIntegerField(default=0)
    program_count = models.PositiveIntegerField(default=0)
    program_tag_count = models.PositiveIntegerField(default=0)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["run", "name"], name="unique_mine_controller_per_run")]
        ordering = ["run", "name"]

    def __str__(self) -> str:
        return f"{self.run_id}: {self.name}"


class PlcDataTypeFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="plc_data_types")
    controller = models.ForeignKey(PlcControllerFact, on_delete=models.CASCADE, related_name="data_types")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_aoi = models.BooleanField(default=False)
    member_count = models.PositiveIntegerField(default=0)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["controller", "name"], name="unique_mine_type_per_controller")]
        ordering = ["controller", "name"]

    def __str__(self) -> str:
        return f"{self.controller.name}.{self.name}"


class PlcMemberFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="plc_members")
    data_type = models.ForeignKey(PlcDataTypeFact, on_delete=models.CASCADE, related_name="members")
    name = models.CharField(max_length=255)
    data_type_name = models.CharField(max_length=255)
    array_dimensions = models.JSONField(default=list, blank=True)
    hidden = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    target = models.CharField(max_length=255, blank=True)
    bit_number = models.IntegerField(blank=True, null=True)
    external_access = models.CharField(max_length=120, blank=True)
    usage = models.CharField(max_length=80, blank=True)
    required = models.BooleanField(blank=True, null=True)
    visible = models.BooleanField(blank=True, null=True)
    constant = models.BooleanField(blank=True, null=True)
    radix = models.CharField(max_length=80, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["data_type", "name"], name="unique_mine_member_per_type")]
        ordering = ["data_type", "name"]


class PlcTagFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="plc_tags")
    controller = models.ForeignKey(PlcControllerFact, on_delete=models.CASCADE, related_name="tags")
    scope = models.CharField(max_length=255, default="Global")
    name = models.CharField(max_length=255)
    data_type_name = models.CharField(max_length=255)
    tag_type = models.CharField(max_length=80, default="Base")
    array_dimensions = models.JSONField(default=list, blank=True)
    alias_for = models.CharField(max_length=1200, blank=True)
    hidden = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    external_access = models.CharField(max_length=120, blank=True)
    constant = models.BooleanField(blank=True, null=True)
    radix = models.CharField(max_length=80, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["controller", "scope", "name"], name="unique_mine_tag_per_scope")]
        ordering = ["controller", "scope", "name"]
        indexes = [models.Index(fields=["run", "scope", "name"], name="mine_tag_lookup_idx")]

    def __str__(self) -> str:
        return self.name if self.scope == "Global" else f"{self.scope}.{self.name}"


class HmiScreenFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_screens")
    name = models.CharField(max_length=255)
    screen_type = models.CharField(max_length=80, default="display")
    source_path = models.CharField(max_length=1200)
    width = models.FloatField(blank=True, null=True)
    height = models.FloatField(blank=True, null=True)
    component_count = models.PositiveIntegerField(default=0)
    tag_reference_count = models.PositiveIntegerField(default=0)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["run", "source_path"], name="unique_mine_screen_per_run_path")]
        ordering = ["run", "name"]

    def __str__(self) -> str:
        return self.name


class HmiComponentFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_components")
    screen = models.ForeignKey(HmiScreenFact, on_delete=models.CASCADE, related_name="components")
    name = models.CharField(max_length=255)
    component_type = models.CharField(max_length=120)
    bounds = models.JSONField(default=dict, blank=True)
    global_object_reference = models.CharField(max_length=1200, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["screen", "id"]
        indexes = [models.Index(fields=["run", "component_type"], name="mine_hmi_component_type_idx")]

    def __str__(self) -> str:
        return f"{self.screen.name}: {self.name}"


class HmiTagReferenceFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_tag_references")
    screen = models.ForeignKey(HmiScreenFact, on_delete=models.CASCADE, related_name="tag_references", blank=True, null=True)
    component = models.ForeignKey(
        HmiComponentFact,
        on_delete=models.CASCADE,
        related_name="tag_references",
        blank=True,
        null=True,
    )
    original = models.CharField(max_length=1200)
    shortcut = models.CharField(max_length=120)
    scope = models.CharField(max_length=255, default="Global")
    base_tag = models.CharField(max_length=255)
    member_path = models.CharField(max_length=1200, blank=True)
    raw_tag_path = models.CharField(max_length=1200, blank=True)
    occurrence_count = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["run", "screen", "component", "base_tag"]
        indexes = [
            models.Index(fields=["run", "shortcut", "base_tag"], name="mine_hmi_ref_tag_idx"),
            models.Index(fields=["run", "scope", "base_tag"], name="mine_hmi_ref_scope_idx"),
        ]

    def __str__(self) -> str:
        return self.original


class HmiParameterFileFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_parameter_files")
    name = models.CharField(max_length=255)
    source_path = models.CharField(max_length=1200)
    parameter_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["run", "source_path"], name="unique_mine_param_file_per_run")]
        ordering = ["run", "name"]


class HmiParameterFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_parameters")
    parameter_file = models.ForeignKey(HmiParameterFileFact, on_delete=models.CASCADE, related_name="parameters")
    name = models.CharField(max_length=80)
    value = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["parameter_file", "name"], name="unique_mine_parameter_per_file")]
        ordering = ["parameter_file", "name"]
