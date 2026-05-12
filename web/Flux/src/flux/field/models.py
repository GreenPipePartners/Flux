from django.db import models
from django.utils import timezone

class FieldEndpoint(models.Model):
    class Status(models.TextChoices):
        DISABLED = "disabled", "Disabled"
        STARTING = "starting", "Starting"
        RUNNING = "running", "Running"
        ERROR = "error", "Error"

    name = models.CharField(max_length=120, unique=True)
    endpoint_url = models.CharField(max_length=255, default="opc.tcp://0.0.0.0:4840/flux/field")
    application_uri = models.CharField(max_length=255, default="urn:flux:field")
    product_uri = models.CharField(max_length=255, default="urn:flux:field")
    namespace_uri = models.CharField(max_length=255, default="urn:flux:field:sim")
    enabled = models.BooleanField(default=True)
    security_policy = models.CharField(max_length=120, default="None")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DISABLED)
    last_seen_at = models.DateTimeField(blank=True, null=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class FieldDevice(models.Model):
    endpoint = models.ForeignKey(FieldEndpoint, on_delete=models.CASCADE, related_name="devices")
    name = models.CharField(max_length=120)
    device_type = models.CharField(max_length=120, default="ControlLogix")
    browse_path = models.CharField(max_length=1000, default="Devices")
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["endpoint", "name"], name="unique_field_device")]
        ordering = ["endpoint", "name"]

    def __str__(self) -> str:
        return f"{self.endpoint}: {self.name}"


class FieldTag(models.Model):
    class DataType(models.TextChoices):
        BOOL = "bool", "Boolean"
        INT = "int", "Integer"
        FLOAT = "float", "Float"
        STRING = "string", "String"

    class SimulationType(models.TextChoices):
        TOGGLE = "toggle", "Toggle"
        RAMP = "ramp", "Ramp"
        WAVE = "wave", "Wave"
        RANDOM_WALK = "random_walk", "Random walk"
        STATIC = "static", "Static"

    device = models.ForeignKey(FieldDevice, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=255)
    data_type = models.CharField(max_length=20, choices=DataType.choices)
    update_rate_ms = models.PositiveIntegerField(default=1000)
    simulation_type = models.CharField(max_length=40, choices=SimulationType.choices, default=SimulationType.RAMP)
    min_value = models.FloatField(blank=True, null=True)
    max_value = models.FloatField(blank=True, null=True)
    variance = models.FloatField(default=0.0)
    initial_value = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    last_value = models.JSONField(blank=True, null=True)
    last_published_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["device", "name"], name="unique_field_device_tag")]
        ordering = ["device", "name"]

    @property
    def opc_item_path(self) -> str:
        return f"{self.device.name}/{self.name}"

    @property
    def node_id(self) -> str:
        return f"ns=2;s={self.device.name}.{self.name}"

    @property
    def browse_name(self) -> str:
        return self.name

    @property
    def ignition_data_type(self) -> str:
        return {
            self.DataType.BOOL: "Boolean",
            self.DataType.INT: "Int4",
            self.DataType.FLOAT: "Float8",
            self.DataType.STRING: "String",
        }[self.data_type]

    def __str__(self) -> str:
        return f"{self.device.name}.{self.name}"


class FieldNode(models.Model):
    endpoint = models.ForeignKey(FieldEndpoint, on_delete=models.CASCADE, related_name="nodes")
    field_tag = models.ForeignKey(
        FieldTag,
        on_delete=models.CASCADE,
        related_name="nodes",
        blank=True,
        null=True,
    )
    node_id = models.CharField(max_length=255)
    browse_name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    folder_path = models.CharField(max_length=1000, default="FluxSim")
    enabled = models.BooleanField(default=True)
    last_published_value = models.JSONField(blank=True, null=True)
    last_published_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["endpoint", "node_id"], name="unique_field_node_id"),
        ]
        ordering = ["endpoint", "folder_path", "browse_name"]

    @property
    def label(self) -> str:
        return self.display_name or self.browse_name

    def __str__(self) -> str:
        return f"{self.endpoint}: {self.node_id}"


class FieldAgentHeartbeat(models.Model):
    endpoint = models.ForeignKey(FieldEndpoint, on_delete=models.CASCADE, related_name="heartbeats")
    instance_id = models.CharField(max_length=120)
    process_id = models.PositiveIntegerField(blank=True, null=True)
    version = models.CharField(max_length=80, blank=True)
    started_at = models.DateTimeField(blank=True, null=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    current_node_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["endpoint", "instance_id"], name="unique_field_agent_instance")
        ]
        ordering = ["endpoint", "instance_id"]

    def __str__(self) -> str:
        return f"{self.endpoint} ({self.instance_id})"
