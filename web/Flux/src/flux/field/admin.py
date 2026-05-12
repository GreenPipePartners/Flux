from django.contrib import admin

from .models import FieldAgentHeartbeat, FieldDevice, FieldEndpoint, FieldNode, FieldTag


class FieldDeviceInline(admin.TabularInline):
    model = FieldDevice
    extra = 0
    fields = ("name", "device_type", "browse_path", "enabled")
    show_change_link = True


class FieldTagInline(admin.TabularInline):
    model = FieldTag
    extra = 0
    fields = (
        "name",
        "data_type",
        "update_rate_ms",
        "simulation_type",
        "min_value",
        "max_value",
        "variance",
        "enabled",
    )
    show_change_link = True


@admin.register(FieldEndpoint)
class FieldEndpointAdmin(admin.ModelAdmin):
    list_display = ("name", "endpoint_url", "enabled", "security_policy", "status", "last_seen_at")
    list_filter = ("enabled", "security_policy", "status")
    search_fields = ("name", "endpoint_url", "application_uri", "namespace_uri", "last_error")
    inlines = (FieldDeviceInline,)


@admin.register(FieldDevice)
class FieldDeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "endpoint", "device_type", "enabled")
    list_filter = ("enabled", "device_type", "endpoint")
    search_fields = ("name", "description")
    inlines = (FieldTagInline,)


@admin.register(FieldTag)
class FieldTagAdmin(admin.ModelAdmin):
    list_display = ("name", "device", "data_type", "simulation_type", "update_rate_ms", "enabled")
    list_filter = ("enabled", "data_type", "simulation_type", "device")
    search_fields = ("name", "description")


@admin.register(FieldNode)
class FieldNodeAdmin(admin.ModelAdmin):
    list_display = ("endpoint", "node_id", "browse_name", "field_tag", "enabled", "last_published_value")
    list_filter = ("enabled", "endpoint", "field_tag__data_type")
    search_fields = ("node_id", "browse_name", "display_name", "folder_path")


@admin.register(FieldAgentHeartbeat)
class FieldAgentHeartbeatAdmin(admin.ModelAdmin):
    list_display = ("endpoint", "instance_id", "process_id", "current_node_count", "last_seen_at")
    search_fields = ("instance_id", "version", "last_error")
