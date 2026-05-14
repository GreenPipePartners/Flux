from django.db import models


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
