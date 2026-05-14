from django.contrib import admin

from .models import TagNode, TagProvider, TagSelection


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
