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
        db_table = '"mine"."run"'
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
        db_table = '"mine"."plc_controller"'
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
        db_table = '"mine"."plc_data_type"'
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
        db_table = '"mine"."plc_member"'
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
        db_table = '"mine"."plc_tag"'
        constraints = [models.UniqueConstraint(fields=["controller", "scope", "name"], name="unique_mine_tag_per_scope")]
        ordering = ["controller", "scope", "name"]
        indexes = [models.Index(fields=["run", "scope", "name"], name="mine_tag_lookup_idx")]

    def __str__(self) -> str:
        return self.name if self.scope == "Global" else f"{self.scope}.{self.name}"


class PlcProgramFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="plc_programs")
    controller = models.ForeignKey(PlcControllerFact, on_delete=models.CASCADE, related_name="programs")
    name = models.CharField(max_length=255)
    main_routine_name = models.CharField(max_length=255, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."plc_program"'
        constraints = [models.UniqueConstraint(fields=["controller", "name"], name="unique_mine_program_per_controller")]
        ordering = ["controller", "name"]
        indexes = [models.Index(fields=["run", "name"], name="mine_plc_program_run_idx")]

    def __str__(self) -> str:
        return f"{self.controller.name}.{self.name}"


class PlcTaskFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="plc_tasks")
    controller = models.ForeignKey(PlcControllerFact, on_delete=models.CASCADE, related_name="tasks")
    name = models.CharField(max_length=255)
    task_type = models.CharField(max_length=80, blank=True)
    priority = models.IntegerField(blank=True, null=True)
    rate = models.IntegerField(blank=True, null=True)
    watchdog = models.IntegerField(blank=True, null=True)
    disable_update_outputs = models.BooleanField(blank=True, null=True)
    inhibit_task = models.BooleanField(blank=True, null=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."plc_task"'
        constraints = [models.UniqueConstraint(fields=["controller", "name"], name="unique_mine_task_per_controller")]
        ordering = ["controller", "name"]
        indexes = [models.Index(fields=["run", "task_type"], name="mine_plc_task_type_idx")]

    def __str__(self) -> str:
        return f"{self.controller.name}.{self.name}"


class PlcScheduledProgramFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="plc_scheduled_programs")
    task = models.ForeignKey(PlcTaskFact, on_delete=models.CASCADE, related_name="scheduled_programs")
    program = models.ForeignKey(
        PlcProgramFact,
        on_delete=models.SET_NULL,
        related_name="scheduled_task_links",
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = '"mine"."plc_scheduled_program"'
        constraints = [
            models.UniqueConstraint(fields=["task", "sort_order", "name"], name="unique_mine_task_program_order")
        ]
        ordering = ["task", "sort_order", "name"]
        indexes = [models.Index(fields=["run", "name"], name="mine_plc_sched_program_idx")]


class PlcRoutineFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="plc_routines")
    program = models.ForeignKey(PlcProgramFact, on_delete=models.CASCADE, related_name="routines")
    name = models.CharField(max_length=255)
    routine_type = models.CharField(max_length=80, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."plc_routine"'
        constraints = [models.UniqueConstraint(fields=["program", "name"], name="unique_mine_routine_per_program")]
        ordering = ["program", "name"]
        indexes = [models.Index(fields=["run", "routine_type"], name="mine_plc_routine_type_idx")]

    def __str__(self) -> str:
        return f"{self.program.name}.{self.name}"


class PlcRungFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="plc_rungs")
    routine = models.ForeignKey(PlcRoutineFact, on_delete=models.CASCADE, related_name="rungs")
    number = models.PositiveIntegerField()
    sort_order = models.PositiveIntegerField(default=0)
    rung_type = models.CharField(max_length=80, blank=True)
    text = models.TextField(blank=True)
    comment = models.TextField(blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."plc_rung"'
        constraints = [models.UniqueConstraint(fields=["routine", "number"], name="unique_mine_rung_per_routine")]
        ordering = ["routine", "sort_order", "number"]
        indexes = [models.Index(fields=["run", "rung_type"], name="mine_plc_rung_type_idx")]


class PlcInstructionFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="plc_instructions")
    rung = models.ForeignKey(PlcRungFact, on_delete=models.CASCADE, related_name="instructions")
    sort_order = models.PositiveIntegerField(default=0)
    mnemonic = models.CharField(max_length=80)
    operands = models.JSONField(default=list, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."plc_instruction"'
        constraints = [models.UniqueConstraint(fields=["rung", "sort_order"], name="unique_mine_instruction_order")]
        ordering = ["rung", "sort_order"]
        indexes = [models.Index(fields=["run", "mnemonic"], name="mine_plc_instruction_idx")]


class PlcTagReferenceFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="plc_tag_references")
    rung = models.ForeignKey(PlcRungFact, on_delete=models.CASCADE, related_name="tag_references")
    instruction = models.ForeignKey(PlcInstructionFact, on_delete=models.CASCADE, related_name="tag_references")
    tag = models.ForeignKey(
        PlcTagFact,
        on_delete=models.SET_NULL,
        related_name="plc_references",
        blank=True,
        null=True,
    )
    scope = models.CharField(max_length=255, default="Global")
    original = models.CharField(max_length=1200)
    base_tag = models.CharField(max_length=255)
    member_path = models.CharField(max_length=1200, blank=True)
    operand_index = models.PositiveIntegerField(default=0)
    role = models.CharField(max_length=80, default="unknown")
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."plc_tag_reference"'
        ordering = ["rung", "instruction", "operand_index", "id"]
        indexes = [
            models.Index(fields=["run", "base_tag"], name="mine_plc_ref_tag_idx"),
            models.Index(fields=["run", "role"], name="mine_plc_ref_role_idx"),
            models.Index(fields=["instruction", "operand_index"], name="mine_plc_ref_operand_idx"),
        ]


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
        db_table = '"mine"."hmi_screen"'
        constraints = [models.UniqueConstraint(fields=["run", "source_path"], name="unique_mine_screen_per_run_path")]
        ordering = ["run", "name"]

    def __str__(self) -> str:
        return self.name


class HmiComponentFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_components")
    screen = models.ForeignKey(HmiScreenFact, on_delete=models.CASCADE, related_name="components")
    parent_component = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="child_components",
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=255)
    component_type = models.CharField(max_length=120)
    component_path = models.CharField(max_length=1200, blank=True)
    parent_path = models.CharField(max_length=1200, blank=True)
    depth = models.PositiveIntegerField(default=0)
    sibling_index = models.PositiveIntegerField(default=0)
    children_count = models.PositiveIntegerField(default=0)
    is_group = models.BooleanField(default=False)
    is_global_instance = models.BooleanField(default=False)
    bounds = models.JSONField(default=dict, blank=True)
    geometry = models.JSONField(default=dict, blank=True)
    global_object_reference = models.CharField(max_length=1200, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."hmi_component"'
        ordering = ["screen", "id"]
        indexes = [
            models.Index(fields=["run", "component_type"], name="mine_hmi_component_type_idx"),
            models.Index(fields=["run", "screen", "parent_path"], name="mine_hmi_parent_path_idx"),
            models.Index(fields=["screen", "component_path"], name="mine_hmi_component_path_idx"),
        ]

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
    source_kind = models.CharField(max_length=80, default="component")
    source_path = models.CharField(max_length=1200, blank=True)
    occurrence_count = models.PositiveIntegerField(default=1)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."hmi_tag_reference"'
        ordering = ["run", "screen", "component", "base_tag"]
        indexes = [
            models.Index(fields=["run", "shortcut", "base_tag"], name="mine_hmi_ref_tag_idx"),
            models.Index(fields=["run", "scope", "base_tag"], name="mine_hmi_ref_scope_idx"),
            models.Index(fields=["run", "source_kind"], name="mine_hmi_ref_source_idx"),
        ]

    def __str__(self) -> str:
        return self.original


class HmiParameterFileFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_parameter_files")
    name = models.CharField(max_length=255)
    source_path = models.CharField(max_length=1200)
    parameter_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = '"mine"."hmi_parameter_file"'
        constraints = [models.UniqueConstraint(fields=["run", "source_path"], name="unique_mine_param_file_per_run")]
        ordering = ["run", "name"]


class HmiParameterFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_parameters")
    parameter_file = models.ForeignKey(HmiParameterFileFact, on_delete=models.CASCADE, related_name="parameters")
    name = models.CharField(max_length=80)
    value = models.TextField(blank=True)

    class Meta:
        db_table = '"mine"."hmi_parameter"'
        constraints = [models.UniqueConstraint(fields=["parameter_file", "name"], name="unique_mine_parameter_per_file")]
        ordering = ["parameter_file", "name"]


class HmiComponentActionFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_component_actions")
    screen = models.ForeignKey(HmiScreenFact, on_delete=models.CASCADE, related_name="component_actions")
    component = models.ForeignKey(HmiComponentFact, on_delete=models.CASCADE, related_name="actions")
    name = models.CharField(max_length=255)
    action_type = models.CharField(max_length=120, blank=True)
    value = models.TextField(blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."hmi_component_action"'
        ordering = ["component", "id"]
        indexes = [models.Index(fields=["run", "action_type"], name="mine_hmi_action_type_idx")]


class HmiComponentStateFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_component_states")
    screen = models.ForeignKey(HmiScreenFact, on_delete=models.CASCADE, related_name="component_states")
    component = models.ForeignKey(HmiComponentFact, on_delete=models.CASCADE, related_name="states")
    state_id = models.CharField(max_length=120, blank=True)
    value = models.CharField(max_length=255, blank=True)
    caption = models.TextField(blank=True)
    back_color = models.CharField(max_length=120, blank=True)
    border_color = models.CharField(max_length=120, blank=True)
    border_width = models.CharField(max_length=80, blank=True)
    font_size = models.CharField(max_length=80, blank=True)
    font_family = models.CharField(max_length=120, blank=True)
    text_color = models.CharField(max_length=120, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."hmi_component_state"'
        ordering = ["component", "id"]
        indexes = [models.Index(fields=["run", "state_id"], name="mine_hmi_state_id_idx")]


class HmiComponentParameterFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_component_parameters")
    screen = models.ForeignKey(HmiScreenFact, on_delete=models.CASCADE, related_name="component_parameters")
    component = models.ForeignKey(HmiComponentFact, on_delete=models.CASCADE, related_name="parameters")
    name = models.CharField(max_length=120)
    value = models.TextField(blank=True)
    description = models.TextField(blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."hmi_component_parameter"'
        ordering = ["component", "name", "id"]
        indexes = [models.Index(fields=["run", "name"], name="mine_hmi_param_name_idx")]


class HmiGlobalObjectLinkFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_global_object_links")
    screen = models.ForeignKey(HmiScreenFact, on_delete=models.CASCADE, related_name="global_object_links")
    component = models.ForeignKey(HmiComponentFact, on_delete=models.CASCADE, related_name="global_object_links")
    reference = models.CharField(max_length=1200)
    link_file = models.CharField(max_length=1200, blank=True)
    link_object = models.CharField(max_length=1200, blank=True)
    link_base_object = models.CharField(max_length=1200, blank=True)
    link_size = models.CharField(max_length=120, blank=True)
    link_connections = models.TextField(blank=True)
    link_animations = models.TextField(blank=True)
    link_tooltip_text = models.TextField(blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."hmi_global_object_link"'
        ordering = ["component", "id"]
        indexes = [models.Index(fields=["run", "reference"], name="mine_hmi_global_ref_idx")]


class HmiVbaLinkFact(models.Model):
    run = models.ForeignKey(MineRun, on_delete=models.CASCADE, related_name="hmi_vba_links")
    screen = models.ForeignKey(HmiScreenFact, on_delete=models.CASCADE, related_name="vba_links")
    component = models.ForeignKey(HmiComponentFact, on_delete=models.CASCADE, related_name="vba_links")
    name = models.CharField(max_length=255)
    value = models.TextField(blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"mine"."hmi_vba_link"'
        ordering = ["component", "id"]
        indexes = [models.Index(fields=["run", "name"], name="mine_hmi_vba_name_idx")]
