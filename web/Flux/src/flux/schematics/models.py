from __future__ import annotations

from django.db import models


class SchematicSystem(models.Model):
    name = models.CharField(max_length=240)
    slug = models.SlugField(max_length=240, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"schematics"."system"'
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PotentialSystem(models.Model):
    class PolarityKind(models.TextChoices):
        AC = "ac", "AC"
        DC = "dc", "DC"
        MIXED = "mixed", "Mixed"

    key = models.CharField(max_length=80, unique=True)
    label = models.CharField(max_length=160)
    nominal_voltage = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    phase_count = models.PositiveSmallIntegerField(default=1)
    polarity_kind = models.CharField(max_length=20, choices=PolarityKind.choices)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"schematics"."potential_system"'
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class PotentialLabel(models.Model):
    potential_system = models.ForeignKey(PotentialSystem, on_delete=models.CASCADE, related_name="labels")
    key = models.CharField(max_length=40)
    label = models.CharField(max_length=120)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = '"schematics"."potential_label"'
        constraints = [
            models.UniqueConstraint(fields=["potential_system", "key"], name="unique_sch_potential_label")
        ]
        ordering = ["potential_system", "sort_order", "key"]

    def __str__(self) -> str:
        return f"{self.potential_system.key}.{self.key}"


class ComponentTemplate(models.Model):
    key = models.CharField(max_length=120, unique=True)
    label = models.CharField(max_length=180)
    component_kind = models.CharField(max_length=80)
    version = models.PositiveSmallIntegerField(default=1)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"schematics"."component_template"'
        ordering = ["key"]
        indexes = [models.Index(fields=["component_kind"], name="sch_tmpl_kind_idx")]

    def __str__(self) -> str:
        return self.key


class TerminalTemplate(models.Model):
    component_template = models.ForeignKey(ComponentTemplate, on_delete=models.CASCADE, related_name="terminal_templates")
    key = models.CharField(max_length=80)
    label = models.CharField(max_length=120, blank=True)
    terminal_kind = models.CharField(max_length=80, default="conductor")
    required = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = '"schematics"."terminal_template"'
        constraints = [models.UniqueConstraint(fields=["component_template", "key"], name="unique_sch_terminal_template")]
        ordering = ["component_template", "sort_order", "key"]

    def __str__(self) -> str:
        return f"{self.component_template.key}.{self.key}"


class RoleTemplate(models.Model):
    component_template = models.ForeignKey(ComponentTemplate, on_delete=models.CASCADE, related_name="role_templates")
    key = models.CharField(max_length=80)
    label = models.CharField(max_length=160, blank=True)
    circuit_kind = models.CharField(max_length=40)
    role_kind = models.CharField(max_length=80)
    potential_system = models.ForeignKey(PotentialSystem, on_delete=models.PROTECT, related_name="role_templates")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"schematics"."role_template"'
        constraints = [models.UniqueConstraint(fields=["component_template", "key"], name="unique_sch_role_template")]
        ordering = ["component_template", "key"]
        indexes = [
            models.Index(fields=["circuit_kind"], name="sch_role_tmpl_circuit_idx"),
            models.Index(fields=["role_kind"], name="sch_role_tmpl_kind_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.component_template.key}.{self.key}"


class RoleTerminalTemplate(models.Model):
    role_template = models.ForeignKey(RoleTemplate, on_delete=models.CASCADE, related_name="terminal_links")
    terminal_template = models.ForeignKey(TerminalTemplate, on_delete=models.CASCADE, related_name="role_links")
    interface_key = models.CharField(max_length=40, blank=True)
    usage = models.CharField(max_length=40, default="conductor")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = '"schematics"."role_terminal_template"'
        constraints = [
            models.UniqueConstraint(fields=["role_template", "terminal_template"], name="unique_sch_role_terminal_template")
        ]
        ordering = ["role_template", "sort_order", "terminal_template__key"]


class InternalRelationTemplate(models.Model):
    component_template = models.ForeignKey(ComponentTemplate, on_delete=models.CASCADE, related_name="relation_templates")
    key = models.CharField(max_length=120)
    relation_type = models.CharField(max_length=80, default="behavioral")
    source_role_template = models.ForeignKey(RoleTemplate, on_delete=models.CASCADE, related_name="source_relation_templates")
    target_role_template = models.ForeignKey(RoleTemplate, on_delete=models.CASCADE, related_name="target_relation_templates")
    condition_key = models.CharField(max_length=120)
    effect_key = models.CharField(max_length=120)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"schematics"."internal_relation_template"'
        constraints = [models.UniqueConstraint(fields=["component_template", "key"], name="unique_sch_relation_template")]
        ordering = ["component_template", "key"]

    def __str__(self) -> str:
        return f"{self.component_template.key}.{self.key}"


class Component(models.Model):
    system = models.ForeignKey(SchematicSystem, on_delete=models.CASCADE, related_name="components")
    template = models.ForeignKey(ComponentTemplate, on_delete=models.PROTECT, related_name="components")
    reference = models.CharField(max_length=80)
    name = models.CharField(max_length=180, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"schematics"."component"'
        constraints = [models.UniqueConstraint(fields=["system", "reference"], name="unique_sch_component_ref")]
        ordering = ["system", "reference"]

    def __str__(self) -> str:
        return self.reference


class Terminal(models.Model):
    component = models.ForeignKey(Component, on_delete=models.CASCADE, related_name="terminals")
    template = models.ForeignKey(TerminalTemplate, on_delete=models.PROTECT, related_name="terminals")
    key = models.CharField(max_length=80)
    label = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = '"schematics"."terminal"'
        constraints = [models.UniqueConstraint(fields=["component", "key"], name="unique_sch_terminal")]
        ordering = ["component", "template__sort_order", "key"]

    def __str__(self) -> str:
        return f"{self.component.reference}.{self.key}"


class Role(models.Model):
    component = models.ForeignKey(Component, on_delete=models.CASCADE, related_name="roles")
    template = models.ForeignKey(RoleTemplate, on_delete=models.PROTECT, related_name="roles")
    key = models.CharField(max_length=80)
    label = models.CharField(max_length=160, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"schematics"."role"'
        constraints = [models.UniqueConstraint(fields=["component", "key"], name="unique_sch_role")]
        ordering = ["component", "key"]

    def __str__(self) -> str:
        return f"{self.component.reference}.{self.key}"


class RoleTerminal(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="terminal_links")
    terminal = models.ForeignKey(Terminal, on_delete=models.CASCADE, related_name="role_links")
    interface_key = models.CharField(max_length=40, blank=True)
    usage = models.CharField(max_length=40, default="conductor")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = '"schematics"."role_terminal"'
        constraints = [models.UniqueConstraint(fields=["role", "terminal"], name="unique_sch_role_terminal")]
        ordering = ["role", "sort_order", "terminal__key"]


class InternalRelation(models.Model):
    component = models.ForeignKey(Component, on_delete=models.CASCADE, related_name="internal_relations")
    template = models.ForeignKey(InternalRelationTemplate, on_delete=models.PROTECT, related_name="relations")
    key = models.CharField(max_length=120)
    relation_type = models.CharField(max_length=80, default="behavioral")
    source_role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="source_relations")
    target_role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="target_relations")
    condition_key = models.CharField(max_length=120)
    effect_key = models.CharField(max_length=120)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"schematics"."internal_relation"'
        constraints = [models.UniqueConstraint(fields=["component", "key"], name="unique_sch_relation")]
        ordering = ["component", "key"]


class Source(models.Model):
    system = models.ForeignKey(SchematicSystem, on_delete=models.CASCADE, related_name="sources")
    name = models.CharField(max_length=180)
    source_kind = models.CharField(max_length=80)
    potential_system = models.ForeignKey(PotentialSystem, on_delete=models.PROTECT, related_name="sources")
    producer_component = models.ForeignKey(Component, on_delete=models.PROTECT, related_name="produced_sources", blank=True, null=True)
    producer_role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="produced_sources", blank=True, null=True)
    nominal_voltage = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    phase_count = models.PositiveSmallIntegerField(default=1)
    polarity_kind = models.CharField(max_length=20, choices=PotentialSystem.PolarityKind.choices)
    design_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = '"schematics"."source"'
        constraints = [models.UniqueConstraint(fields=["system", "name"], name="unique_sch_source")]
        ordering = ["system", "name"]

    def __str__(self) -> str:
        return self.name


class SourcePotential(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="potentials")
    potential_label = models.ForeignKey(PotentialLabel, on_delete=models.PROTECT, related_name="source_potentials")
    key = models.CharField(max_length=40)
    label = models.CharField(max_length=120, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = '"schematics"."source_potential"'
        constraints = [models.UniqueConstraint(fields=["source", "key"], name="unique_sch_source_potential")]
        ordering = ["source", "sort_order", "key"]


class Circuit(models.Model):
    system = models.ForeignKey(SchematicSystem, on_delete=models.CASCADE, related_name="circuits")
    name = models.CharField(max_length=180)
    circuit_kind = models.CharField(max_length=40)
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="circuits")
    potential_system = models.ForeignKey(PotentialSystem, on_delete=models.PROTECT, related_name="circuits")
    allow_multiple_sources = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = '"schematics"."circuit"'
        constraints = [models.UniqueConstraint(fields=["system", "name"], name="unique_sch_circuit")]
        ordering = ["system", "sort_order", "name"]
        indexes = [models.Index(fields=["circuit_kind"], name="sch_circuit_kind_idx")]

    def __str__(self) -> str:
        return self.name


class CircuitPotential(models.Model):
    circuit = models.ForeignKey(Circuit, on_delete=models.CASCADE, related_name="potentials")
    potential_label = models.ForeignKey(PotentialLabel, on_delete=models.PROTECT, related_name="circuit_potentials")
    key = models.CharField(max_length=40)
    label = models.CharField(max_length=120, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = '"schematics"."circuit_potential"'
        constraints = [models.UniqueConstraint(fields=["circuit", "key"], name="unique_sch_circuit_potential")]
        ordering = ["circuit", "sort_order", "key"]


class CircuitParticipant(models.Model):
    circuit = models.ForeignKey(Circuit, on_delete=models.CASCADE, related_name="participants")
    component = models.ForeignKey(Component, on_delete=models.CASCADE, related_name="circuit_participations")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="circuit_participations")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = '"schematics"."circuit_participant"'
        constraints = [models.UniqueConstraint(fields=["circuit", "role"], name="unique_sch_circuit_role")]
        ordering = ["circuit", "sort_order", "component__reference"]


class Net(models.Model):
    circuit = models.ForeignKey(Circuit, on_delete=models.CASCADE, related_name="nets")
    key = models.CharField(max_length=120)
    label = models.CharField(max_length=180, blank=True)
    circuit_potential = models.ForeignKey(CircuitPotential, on_delete=models.PROTECT, related_name="nets", blank=True, null=True)

    class Meta:
        db_table = '"schematics"."net"'
        constraints = [models.UniqueConstraint(fields=["circuit", "key"], name="unique_sch_net")]
        ordering = ["circuit", "key"]


class Connection(models.Model):
    circuit = models.ForeignKey(Circuit, on_delete=models.CASCADE, related_name="connections")
    net = models.ForeignKey(Net, on_delete=models.CASCADE, related_name="connections", blank=True, null=True)
    from_terminal = models.ForeignKey(Terminal, on_delete=models.CASCADE, related_name="outgoing_connections")
    to_terminal = models.ForeignKey(Terminal, on_delete=models.CASCADE, related_name="incoming_connections")
    connection_kind = models.CharField(max_length=80, default="conductor")
    condition_key = models.CharField(max_length=120, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"schematics"."connection"'
        ordering = ["circuit", "id"]
        indexes = [models.Index(fields=["circuit", "connection_kind"], name="sch_connection_kind_idx")]


class CompileRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    system = models.ForeignKey(SchematicSystem, on_delete=models.CASCADE, related_name="compile_runs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    summary = models.JSONField(default=dict, blank=True)
    finding_count = models.PositiveIntegerField(default=0)
    binding_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = '"schematics"."compile_run"'
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["system", "status"], name="sch_compile_status_idx")]


class ValidationFinding(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    compile_run = models.ForeignKey(CompileRun, on_delete=models.CASCADE, related_name="findings")
    severity = models.CharField(max_length=20, choices=Severity.choices)
    code = models.CharField(max_length=120)
    message = models.TextField()
    object_kind = models.CharField(max_length=80, blank=True)
    object_id = models.PositiveBigIntegerField(blank=True, null=True)
    path = models.CharField(max_length=600, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"schematics"."validation_finding"'
        ordering = ["compile_run", "severity", "code", "id"]
        indexes = [models.Index(fields=["compile_run", "severity"], name="sch_finding_severity_idx")]


class TerminalPotentialBinding(models.Model):
    compile_run = models.ForeignKey(CompileRun, on_delete=models.CASCADE, related_name="terminal_bindings")
    circuit = models.ForeignKey(Circuit, on_delete=models.CASCADE, related_name="terminal_bindings")
    terminal = models.ForeignKey(Terminal, on_delete=models.CASCADE, related_name="potential_bindings")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="potential_bindings")
    circuit_potential = models.ForeignKey(CircuitPotential, on_delete=models.PROTECT, related_name="terminal_bindings")
    condition_key = models.CharField(max_length=120, blank=True)
    binding_kind = models.CharField(max_length=80, default="interface")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"schematics"."terminal_potential_binding"'
        constraints = [
            models.UniqueConstraint(
                fields=["compile_run", "terminal", "role", "circuit_potential", "condition_key"],
                name="unique_sch_terminal_binding",
            )
        ]
        ordering = ["compile_run", "circuit", "terminal__component__reference", "terminal__key"]
