from django.db import models
from django.utils import timezone
from flux_sim.tag_mode import TagModeKind


class TagProvider(models.Model):
    class Source(models.TextChoices):
        JSON_UPLOAD = "json_upload", "JSON upload"
        IGNITION_PROVIDER = "ignition_provider", "Ignition provider"

    name = models.CharField(max_length=120, unique=True)
    source = models.CharField(max_length=40, choices=Source.choices)
    source_name = models.CharField(max_length=255, blank=True)
    source_sha256 = models.CharField(max_length=64)
    root_tag_type = models.CharField(max_length=80, default="Provider")
    total_nodes = models.PositiveIntegerField(default=0)
    folder_count = models.PositiveIntegerField(default=0)
    atomic_tag_count = models.PositiveIntegerField(default=0)
    udt_instance_count = models.PositiveIntegerField(default=0)
    udt_type_count = models.PositiveIntegerField(default=0)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TagNode(models.Model):
    provider = models.ForeignKey(TagProvider, on_delete=models.CASCADE, related_name="nodes")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        blank=True,
        null=True,
    )
    path = models.CharField(max_length=1200)
    name = models.CharField(max_length=255, blank=True)
    tag_type = models.CharField(max_length=80)
    data_type = models.CharField(max_length=80, blank=True)
    value_source = models.CharField(max_length=80, blank=True)
    type_id = models.CharField(max_length=1200, blank=True)
    opc_server = models.CharField(max_length=255, blank=True)
    opc_item_path = models.CharField(max_length=1200, blank=True)
    source_tag_path = models.CharField(max_length=1200, blank=True)
    expression = models.TextField(blank=True)
    engineering_units = models.CharField(max_length=80, blank=True)
    documentation = models.TextField(blank=True)
    tooltip = models.TextField(blank=True)
    parameters = models.JSONField(blank=True, null=True)
    value = models.JSONField(blank=True, null=True)
    raw_config = models.JSONField(default=dict, blank=True)
    depth = models.PositiveSmallIntegerField(default=0)
    sort_order = models.PositiveIntegerField(default=0)
    has_children = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "path"], name="unique_base_tag_node_path")]
        indexes = [
            models.Index(fields=["provider", "parent"]),
            models.Index(fields=["provider", "tag_type"]),
            models.Index(fields=["provider", "value_source"]),
            models.Index(fields=["provider", "data_type"]),
        ]
        ordering = ["provider", "depth", "sort_order", "name"]

    @property
    def full_path(self) -> str:
        return f"[{self.provider.name}]{self.path}" if self.path else f"[{self.provider.name}]"

    def __str__(self) -> str:
        return self.full_path


class TagSelection(models.Model):
    class Purpose(models.TextChoices):
        SIM = "sim", "Simulation"
        RUNTIME = "runtime", "Runtime"
        FIELD = "field", "Field"

    provider = models.ForeignKey(TagProvider, on_delete=models.CASCADE, related_name="selections")
    path = models.CharField(max_length=1200)
    purpose = models.CharField(max_length=40, choices=Purpose.choices, default=Purpose.SIM)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "purpose", "path"], name="unique_base_tag_selection")
        ]
        ordering = ["provider", "purpose", "path"]

    def __str__(self) -> str:
        return f"{self.provider.name}:{self.purpose}:{self.path}"


class SimDriver(models.Model):
    key = models.CharField(max_length=80, unique=True)
    label = models.CharField(max_length=120)
    strategy_key = models.CharField(max_length=80, default="generic")
    ignition_driver_names = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.label


class SimDevice(models.Model):
    class Mode(models.TextChoices):
        STANDARD = "standard", "Standard"
        SLOW_NETWORK = "slow_network", "Slow network"

    provider = models.ForeignKey(TagProvider, on_delete=models.CASCADE, related_name="sim_devices")
    name = models.CharField(max_length=120)
    driver = models.ForeignKey(SimDriver, on_delete=models.PROTECT, related_name="devices")
    opc_server_name = models.CharField(max_length=255, blank=True)
    endpoint_url = models.CharField(max_length=255, blank=True)
    namespace_uri = models.CharField(max_length=255, blank=True)
    mode = models.CharField(max_length=40, choices=Mode.choices, default=Mode.STANDARD)
    response_delay_ms = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    source_status = models.CharField(max_length=255, blank=True)
    source_detail = models.TextField(blank=True)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "name"], name="unique_base_sim_device")]
        indexes = [models.Index(fields=["provider", "driver"])]
        ordering = ["provider", "name"]

    def __str__(self) -> str:
        return f"{self.provider.name}: {self.name}"


class SimDeviceTag(models.Model):
    class Behavior(models.TextChoices):
        IMMEDIATE = TagModeKind.IMMEDIATE, "Immediate"
        SLOW_RESPONSE = TagModeKind.SLOW_RESPONSE, "Slow response"
        IGNORES_WRITE = TagModeKind.IGNORES_WRITE, "Ignores tag write"
        WRITE_TO_OTHER_TAG_RESPONSE = TagModeKind.WRITE_TO_OTHER_TAG_RESPONSE, "Write to other tag response"

    provider = models.ForeignKey(TagProvider, on_delete=models.CASCADE, related_name="sim_device_tags")
    device = models.ForeignKey(SimDevice, on_delete=models.CASCADE, related_name="tags")
    tag_node = models.ForeignKey(
        TagNode,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="sim_device_tags",
    )
    source_path = models.CharField(max_length=1200)
    tag_name = models.CharField(max_length=255)
    data_type = models.CharField(max_length=80, blank=True)
    value_source = models.CharField(max_length=80, blank=True)
    opc_server = models.CharField(max_length=255, blank=True)
    opc_item_path = models.CharField(max_length=1200, blank=True)
    address_strategy = models.CharField(max_length=80, default="generic")
    address = models.JSONField(default=dict, blank=True)
    behavior = models.CharField(max_length=40, choices=Behavior.choices, default=Behavior.IMMEDIATE)
    mode_config = models.JSONField(blank=True, null=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "source_path"], name="unique_base_sim_device_tag_source")]
        indexes = [
            models.Index(fields=["provider", "device"]),
            models.Index(fields=["provider", "address_strategy"]),
        ]
        ordering = ["provider", "device", "source_path"]

    def __str__(self) -> str:
        return f"{self.device.name}: {self.source_path}"


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
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["endpoint", "name"], name="unique_base_field_device")]
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
    config = models.JSONField(default=dict, blank=True)
    last_value = models.JSONField(blank=True, null=True)
    last_published_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["device", "name"], name="unique_base_field_device_tag")]
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
            models.UniqueConstraint(fields=["endpoint", "node_id"], name="unique_base_field_node_id"),
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
            models.UniqueConstraint(fields=["endpoint", "instance_id"], name="unique_base_field_agent_instance")
        ]
        ordering = ["endpoint", "instance_id"]

    def __str__(self) -> str:
        return f"{self.endpoint} ({self.instance_id})"
