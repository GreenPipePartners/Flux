from django.contrib import admin

from .models import DeviceConfig, Driver, Provider, ProviderNode, ProviderSelection, Server, TagConfig


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "sim_server", "source", "source_name", "total_nodes", "atomic_tag_count", "imported_at")
    list_filter = ("source", "sim_server")
    search_fields = ("name", "source_name")


@admin.register(ProviderNode)
class ProviderNodeAdmin(admin.ModelAdmin):
    list_display = ("provider", "path", "tag_type", "data_type", "value_source", "has_children")
    list_filter = ("provider", "tag_type", "value_source", "data_type")
    search_fields = ("provider__name", "path", "name", "opc_item_path", "type_id")
    list_select_related = ("provider", "parent")


@admin.register(ProviderSelection)
class ProviderSelectionAdmin(admin.ModelAdmin):
    list_display = ("provider", "purpose", "path", "enabled", "updated_at")
    list_filter = ("purpose", "enabled", "provider")
    search_fields = ("provider__name", "path")
    list_select_related = ("provider",)


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ("name", "endpoint_url", "enabled", "security_policy")
    list_filter = ("enabled", "security_policy")
    search_fields = ("name", "endpoint_url", "namespace_uri")


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "strategy_key")
    list_filter = ("strategy_key",)
    search_fields = ("key", "label", "ignition_driver_names")


class TagConfigInline(admin.TabularInline):
    model = TagConfig
    extra = 0


@admin.register(DeviceConfig)
class DeviceConfigAdmin(admin.ModelAdmin):
    list_display = ("base_device", "endpoint", "source_provider", "mode", "enabled", "updated_at")
    list_filter = ("enabled", "mode", "endpoint", "source_provider")
    search_fields = ("base_device__name", "base_device__namespace", "browse_path")
    list_select_related = ("base_device", "endpoint", "source_provider", "sim_server", "driver")
    inlines = (TagConfigInline,)


@admin.register(TagConfig)
class TagConfigAdmin(admin.ModelAdmin):
    list_display = ("base_tag", "sim_device", "simulation_type", "behavior", "enabled")
    list_filter = ("enabled", "simulation_type", "behavior")
    search_fields = ("base_tag__name", "base_tag__tagpath", "source_path")
    list_select_related = ("base_tag", "sim_device", "sim_device__base_device")
