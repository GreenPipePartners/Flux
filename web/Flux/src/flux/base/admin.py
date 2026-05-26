from django.contrib import admin

from flux.serve.models import FieldAgentHeartbeat
from flux.sim.models import FieldEndpoint

from .models import Device, Entity, Tag


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ("kind", "natural_key", "display_name", "retired_at", "updated_at")
    list_filter = ("kind", "retired_at")
    search_fields = ("natural_key", "display_name", "guid")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "namespace", "device_type", "entity", "enabled", "updated_at")
    list_filter = ("enabled", "namespace", "device_type")
    search_fields = ("name", "namespace", "description")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "tagpath", "entity", "device", "data_type", "update_rate_ms", "enabled")
    list_filter = ("enabled", "provider", "data_type")
    search_fields = ("name", "provider", "tagpath", "full_path", "device__name")
    list_select_related = ("device",)


@admin.register(FieldEndpoint)
class FieldEndpointAdmin(admin.ModelAdmin):
    list_display = ("name", "endpoint_url", "enabled", "status", "last_seen_at")
    list_filter = ("enabled", "status")
    search_fields = ("name", "endpoint_url")


@admin.register(FieldAgentHeartbeat)
class FieldAgentHeartbeatAdmin(admin.ModelAdmin):
    list_display = ("endpoint", "instance_id", "process_id", "version", "current_node_count", "last_seen_at")
    list_filter = ("endpoint",)
    search_fields = ("instance_id", "endpoint__name")
