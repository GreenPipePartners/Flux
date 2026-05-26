import uuid
from hashlib import sha256

from django.db import models


class Entity(models.Model):
    class Kind(models.TextChoices):
        BASE_TAG = "base.tag", "Base tag"
        BASE_DEVICE = "base.device", "Base device"
        PLANE_SERIES = "plane.series", "Plane series"
        BRIDGE_CONNECTION = "bridge.connection", "Bridge connection"
        SERVE_WORKER = "serve.worker", "Serve worker"
        FIELD_ENDPOINT = "field.endpoint", "Field endpoint"
        SIM_DEVICE = "sim.device", "Sim device"

    guid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    kind = models.CharField(max_length=80, choices=Kind.choices)
    natural_key = models.TextField()
    natural_key_hash = models.CharField(max_length=64)
    display_name = models.CharField(max_length=255)
    retired_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"base"."entity"'
        constraints = [models.UniqueConstraint(fields=["kind", "natural_key_hash"], name="unique_base_entity_kind_key_hash")]
        indexes = [
            models.Index(fields=["kind", "display_name"], name="base_entity_kind_name_idx"),
            models.Index(fields=["retired_at"], name="base_entity_retired_idx"),
        ]
        ordering = ["kind", "natural_key"]

    def __str__(self) -> str:
        return f"{self.kind}:{self.natural_key}"

    def save(self, *args, **kwargs):
        self.natural_key_hash = entity_key_hash(self.kind, self.natural_key)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "natural_key_hash" not in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"natural_key_hash"}
        super().save(*args, **kwargs)


def entity_key_hash(kind: str, natural_key: str) -> str:
    return sha256(f"{kind}\0{natural_key}".encode("utf-8")).hexdigest()


class Device(models.Model):
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="device", blank=True, null=True)
    guid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    namespace = models.CharField(max_length=255, default="default")
    name = models.CharField(max_length=120)
    device_type = models.CharField(max_length=120, default="generic")
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"base"."device"'
        constraints = [models.UniqueConstraint(fields=["namespace", "name"], name="unique_base_device_namespace_name")]
        indexes = [
            models.Index(fields=["namespace", "name"], name="base_device_namespace_name_idx"),
            models.Index(fields=["device_type"], name="base_device_type_idx"),
            models.Index(fields=["enabled"], name="base_device_enabled_idx"),
        ]
        ordering = ["namespace", "name"]

    def __str__(self) -> str:
        return f"{self.namespace}:{self.name}"


class Tag(models.Model):
    class DataType(models.TextChoices):
        BOOL = "bool", "Boolean"
        INT = "int", "Integer"
        FLOAT = "float", "Float"
        STRING = "string", "String"

    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="tag", blank=True, null=True)
    guid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, related_name="tags", blank=True, null=True)
    provider = models.CharField(max_length=120, default="default")
    tagpath = models.CharField(max_length=1200)
    full_path = models.CharField(max_length=1400)
    name = models.CharField(max_length=255)
    data_type = models.CharField(max_length=80, blank=True)
    update_rate_ms = models.PositiveIntegerField(default=1000)
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"base"."tag"'
        constraints = [models.UniqueConstraint(fields=["provider", "tagpath"], name="unique_base_tag_provider_path")]
        indexes = [
            models.Index(fields=["device", "name"], name="base_tag_device_name_idx"),
            models.Index(fields=["provider", "name"], name="base_tag_provider_name_idx"),
            models.Index(fields=["enabled"], name="base_tag_enabled_idx"),
        ]
        ordering = ["provider", "tagpath"]

    def __str__(self) -> str:
        return self.full_path

    @property
    def ignition_data_type(self) -> str:
        return {
            self.DataType.BOOL: "Boolean",
            self.DataType.INT: "Int4",
            self.DataType.FLOAT: "Float8",
            self.DataType.STRING: "String",
        }.get(self.data_type, "String")
