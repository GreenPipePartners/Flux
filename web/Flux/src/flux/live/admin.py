from django.contrib import admin

from .models import LiveCardDefinition, LiveCardPointDefinition, LiveScope


class LiveCardPointInline(admin.TabularInline):
    model = LiveCardPointDefinition
    extra = 0


@admin.register(LiveScope)
class LiveScopeAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "enabled", "updated_at")
    search_fields = ("slug", "name")


@admin.register(LiveCardDefinition)
class LiveCardDefinitionAdmin(admin.ModelAdmin):
    list_display = ("scope", "title", "group", "kind", "sort_order", "enabled")
    list_filter = ("scope", "kind", "enabled")
    search_fields = ("title", "group", "kind")
    inlines = [LiveCardPointInline]


@admin.register(LiveCardPointDefinition)
class LiveCardPointDefinitionAdmin(admin.ModelAdmin):
    list_display = ("card", "label", "full_path", "sort_order", "enabled")
    list_filter = ("enabled",)
    search_fields = ("label", "full_path")
