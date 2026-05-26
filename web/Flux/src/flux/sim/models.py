from django.db import models
from django.utils import timezone
from flux_sim.tag_mode import TagModeKind


class Server(models.Model):
    name = models.CharField(max_length=120, unique=True)
    endpoint_url = models.CharField(max_length=255, default="opc.tcp://0.0.0.0:4840/flux/sim")
    application_uri = models.CharField(max_length=255, default="urn:flux:sim")
    product_uri = models.CharField(max_length=255, default="urn:flux:sim")
    namespace_uri = models.CharField(max_length=255, default="urn:flux:sim")
    enabled = models.BooleanField(default=True)
    security_policy = models.CharField(max_length=120, default="None")
    description = models.TextField(blank=True)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"sim"."server"'
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Provider(models.Model):
    class Source(models.TextChoices):
        JSON_UPLOAD = "json_upload", "JSON upload"
        IGNITION_PROVIDER = "ignition_provider", "Ignition provider"

    name = models.CharField(max_length=120, unique=True)
    source = models.CharField(max_length=40, choices=Source.choices)
    source_name = models.CharField(max_length=255, blank=True)
    source_sha256 = models.CharField(max_length=64)
    sim_server = models.ForeignKey(
        Server,
        on_delete=models.PROTECT,
        related_name="tag_providers",
        blank=True,
        null=True,
    )
    root_tag_type = models.CharField(max_length=80, default="Provider")
    total_nodes = models.PositiveIntegerField(default=0)
    folder_count = models.PositiveIntegerField(default=0)
    atomic_tag_count = models.PositiveIntegerField(default=0)
    udt_instance_count = models.PositiveIntegerField(default=0)
    udt_type_count = models.PositiveIntegerField(default=0)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"sim"."provider"'
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ProviderNode(models.Model):
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="nodes")
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
        db_table = '"sim"."provider_node"'
        constraints = [models.UniqueConstraint(fields=["provider", "path"], name="unique_sim_provider_node_path")]
        indexes = [
            models.Index(fields=["provider", "parent"], name="sim_provider_node_parent_idx"),
            models.Index(fields=["provider", "parent", "sort_order"], name="sim_provider_node_sort_idx"),
            models.Index(fields=["provider", "depth", "sort_order"], name="sim_provider_node_depth_idx"),
            models.Index(fields=["provider", "tag_type"], name="sim_provider_node_type_idx"),
            models.Index(fields=["provider", "value_source"], name="sim_provider_node_source_idx"),
            models.Index(fields=["provider", "data_type"], name="sim_provider_node_data_idx"),
        ]
        ordering = ["provider", "depth", "sort_order", "name"]

    @property
    def full_path(self) -> str:
        return f"[{self.provider.name}]{self.path}" if self.path else f"[{self.provider.name}]"

    def __str__(self) -> str:
        return self.full_path


class ProviderSelection(models.Model):
    class Purpose(models.TextChoices):
        SIM = "sim", "Simulation"
        RUNTIME = "runtime", "Runtime"
        FIELD = "field", "Field"

    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="selections")
    path = models.CharField(max_length=1200)
    purpose = models.CharField(max_length=40, choices=Purpose.choices, default=Purpose.SIM)
    enabled = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"sim"."provider_selection"'
        constraints = [
            models.UniqueConstraint(fields=["provider", "purpose", "path"], name="unique_sim_provider_selection_path")
        ]
        ordering = ["provider", "purpose", "path"]

    def __str__(self) -> str:
        return f"{self.provider.name}:{self.purpose}:{self.path}"


class Driver(models.Model):
    key = models.CharField(max_length=80, unique=True)
    label = models.CharField(max_length=120)
    strategy_key = models.CharField(max_length=80, default="generic")
    ignition_driver_names = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = '"sim"."driver"'
        ordering = ["key"]

    def __str__(self) -> str:
        return self.label


class Endpoint(models.Model):
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
        db_table = '"sim"."endpoint"'
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class SimJob(models.Model):
    class Kind(models.TextChoices):
        IMPORT_PROVIDER_JSON = "import_provider_json", "Import provider JSON"
        IMPORT_PROVIDER_IGNITION = "import_provider_ignition", "Import provider from Ignition"
        REMOVE_IGNITION_TAGS = "remove_ignition_tags", "Remove Ignition sim tags"
        APPLY_SELECTION = "apply_selection", "Apply sim selection"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    kind = models.CharField(max_length=80, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    provider = models.CharField(max_length=120, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    input_path = models.CharField(max_length=1200, blank=True)
    progress_current = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(default=0)
    progress_label = models.CharField(max_length=255, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    claimed_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["kind", "status"], name="sim_job_kind_status_idx"),
            models.Index(fields=["status", "created_at"], name="sim_job_status_created_idx"),
        ]

    @property
    def active(self) -> bool:
        return self.status in {self.Status.QUEUED, self.Status.RUNNING}

    def mark_running(self) -> None:
        self.status = self.Status.RUNNING
        self.claimed_at = timezone.now()
        self.save(update_fields=["status", "claimed_at", "updated_at"])

    def __str__(self) -> str:
        return f"{self.kind} ({self.status})"


class DeviceConfig(models.Model):
    class Mode(models.TextChoices):
        STANDARD = "standard", "Standard"
        SLOW_NETWORK = "slow_network", "Slow network"

    base_device = models.OneToOneField("base.Device", on_delete=models.CASCADE, related_name="sim_config")
    endpoint = models.ForeignKey("sim.Endpoint", on_delete=models.SET_NULL, related_name="sim_device_configs", blank=True, null=True)
    source_provider = models.ForeignKey("sim.Provider", on_delete=models.SET_NULL, related_name="sim_device_configs", blank=True, null=True)
    sim_server = models.ForeignKey("sim.Server", on_delete=models.SET_NULL, related_name="sim_device_configs", blank=True, null=True)
    driver = models.ForeignKey("sim.Driver", on_delete=models.SET_NULL, related_name="sim_device_configs", blank=True, null=True)
    browse_path = models.CharField(max_length=1000, default="Devices")
    mode = models.CharField(max_length=40, choices=Mode.choices, default=Mode.STANDARD)
    response_delay_ms = models.PositiveIntegerField(default=0)
    source_status = models.CharField(max_length=255, blank=True)
    source_detail = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"sim"."device"'
        indexes = [
            models.Index(fields=["endpoint"], name="sim_device_endpoint_idx"),
            models.Index(fields=["source_provider"], name="sim_device_provider_idx"),
            models.Index(fields=["enabled"], name="sim_device_enabled_idx"),
        ]
        ordering = ["base_device__namespace", "base_device__name"]

    def __str__(self) -> str:
        return str(self.base_device)

    @property
    def name(self) -> str:
        return self.base_device.name

    @property
    def device_type(self) -> str:
        return self.base_device.device_type


class TagConfig(models.Model):
    class Behavior(models.TextChoices):
        IMMEDIATE = TagModeKind.IMMEDIATE, "Immediate"
        SLOW_RESPONSE = TagModeKind.SLOW_RESPONSE, "Slow response"
        IGNORES_WRITE = TagModeKind.IGNORES_WRITE, "Ignores tag write"
        WRITE_TO_OTHER_TAG_RESPONSE = TagModeKind.WRITE_TO_OTHER_TAG_RESPONSE, "Write to other tag response"

    class SimulationType(models.TextChoices):
        TOGGLE = "toggle", "Toggle"
        RAMP = "ramp", "Ramp"
        WAVE = "wave", "Wave"
        RANDOM_WALK = "random_walk", "Random walk"
        STATIC = "static", "Static"

    sim_device = models.ForeignKey(DeviceConfig, on_delete=models.CASCADE, related_name="tags")
    base_tag = models.ForeignKey("base.Tag", on_delete=models.CASCADE, related_name="sim_configs")
    source_tag_node = models.ForeignKey("sim.ProviderNode", on_delete=models.SET_NULL, related_name="sim_tag_configs", blank=True, null=True)
    source_path = models.CharField(max_length=1200, blank=True)
    tag_name = models.CharField(max_length=255, blank=True)
    simulation_type = models.CharField(max_length=40, choices=SimulationType.choices, default=SimulationType.RAMP)
    min_value = models.FloatField(blank=True, null=True)
    max_value = models.FloatField(blank=True, null=True)
    variance = models.FloatField(default=0.0)
    initial_value = models.CharField(max_length=255, blank=True)
    behavior = models.CharField(max_length=40, choices=Behavior.choices, default=Behavior.IMMEDIATE)
    address_strategy = models.CharField(max_length=80, default="generic")
    address = models.JSONField(default=dict, blank=True)
    mode_config = models.JSONField(blank=True, null=True)
    enabled = models.BooleanField(default=True)
    materialized = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"sim"."tag"'
        constraints = [models.UniqueConstraint(fields=["sim_device", "base_tag"], name="unique_sim_device_tag")]
        indexes = [
            models.Index(fields=["sim_device", "enabled"], name="sim_tag_device_enabled_idx"),
            models.Index(fields=["sim_device", "materialized", "enabled"], name="sim_tag_materialized_idx"),
            models.Index(fields=["simulation_type"], name="sim_tag_sim_type_idx"),
        ]
        ordering = ["sim_device", "base_tag__name"]

    def __str__(self) -> str:
        return str(self.base_tag)

    @property
    def device(self) -> DeviceConfig:
        return self.sim_device

    @property
    def name(self) -> str:
        return self.tag_name or self.base_tag.name

    @property
    def device_name(self) -> str:
        return self.sim_device.base_device.name

    @property
    def data_type(self) -> str:
        return self.base_tag.data_type

    @property
    def update_rate_ms(self) -> int:
        return self.base_tag.update_rate_ms

    @property
    def opc_item_path(self) -> str:
        return f"{self.device_name}/{self.name}"

    @property
    def node_id(self) -> str:
        return f"ns=2;s={self.device_name}.{self.name}"

    @property
    def browse_name(self) -> str:
        return self.name

    @property
    def ignition_data_type(self) -> str:
        return self.base_tag.ignition_data_type


SimServer = Server
TagProvider = Provider
TagNode = ProviderNode
TagSelection = ProviderSelection
SimDriver = Driver
FieldEndpoint = Endpoint
