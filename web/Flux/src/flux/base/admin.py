from django.contrib import admin

from .models import FieldAgentHeartbeat, FieldDevice, FieldEndpoint, FieldNode, FieldTag, TagNode, TagProvider, TagSelection


@admin.register(TagProvider)
class TagProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "source", "source_name", "total_nodes", "atomic_tag_count", "imported_at")
    list_filter = ("source",)
    search_fields = ("name", "source_name")


@admin.register(TagNode)
class TagNodeAdmin(admin.ModelAdmin):
    list_display = ("provider", "path", "tag_type", "data_type", "value_source", "has_children")
    list_filter = ("provider", "tag_type", "value_source", "data_type")
    search_fields = ("provider__name", "path", "name", "opc_item_path", "type_id")
    list_select_related = ("provider", "parent")


@admin.register(TagSelection)
class TagSelectionAdmin(admin.ModelAdmin):
    list_display = ("provider", "purpose", "path", "enabled", "updated_at")
    list_filter = ("purpose", "enabled", "provider")
    search_fields = ("provider__name", "path")
    list_select_related = ("provider",)


class FieldDeviceInline(admin.TabularInline):
    model = FieldDevice
    extra = 0


class FieldTagInline(admin.TabularInline):
    model = FieldTag
    extra = 0


@admin.register(FieldEndpoint)
class FieldEndpointAdmin(admin.ModelAdmin):
    list_display = ("name", "endpoint_url", "enabled", "status", "last_seen_at")
    list_filter = ("enabled", "status")
    search_fields = ("name", "endpoint_url")
    inlines = (FieldDeviceInline,)


@admin.register(FieldDevice)
class FieldDeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "endpoint", "device_type", "browse_path", "enabled")
    list_filter = ("enabled", "device_type", "endpoint")
    search_fields = ("name", "endpoint__name", "browse_path")
    inlines = (FieldTagInline,)


@admin.register(FieldTag)
class FieldTagAdmin(admin.ModelAdmin):
    list_display = ("name", "device", "data_type", "simulation_type", "update_rate_ms", "enabled")
    list_filter = ("enabled", "data_type", "simulation_type", "device__endpoint")
    search_fields = ("name", "device__name", "device__endpoint__name")


@admin.register(FieldNode)
class FieldNodeAdmin(admin.ModelAdmin):
    list_display = ("node_id", "endpoint", "field_tag", "folder_path", "enabled", "last_published_at")
    list_filter = ("enabled", "endpoint")
    search_fields = ("node_id", "browse_name", "display_name", "field_tag__name")


@admin.register(FieldAgentHeartbeat)
class FieldAgentHeartbeatAdmin(admin.ModelAdmin):
    list_display = ("endpoint", "instance_id", "process_id", "version", "current_node_count", "last_seen_at")
    list_filter = ("endpoint",)
    search_fields = ("instance_id", "endpoint__name")
