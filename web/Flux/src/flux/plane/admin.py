from django.contrib import admin

from .models import Latest, Sample, Series, WindowStat


class WindowStatInline(admin.TabularInline):
    model = WindowStat
    extra = 0


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = ("storage_key", "base_tag", "entity", "enabled", "latest_enabled", "history_enabled", "updated_at")
    list_filter = ("enabled", "latest_enabled", "history_enabled", "retention_policy")
    search_fields = ("storage_key", "base_tag__full_path", "base_tag__name", "entity__natural_key")
    list_select_related = ("base_tag", "entity")
    inlines = (WindowStatInline,)


@admin.register(Latest)
class LatestAdmin(admin.ModelAdmin):
    list_display = ("series", "quality_code", "read_at", "updated_at")
    list_filter = ("quality_code",)
    search_fields = ("series__storage_key",)
    list_select_related = ("series",)


@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ("series", "timestamp", "value_float", "quality_code")
    list_filter = ("quality_code",)
    search_fields = ("series__storage_key",)
    list_select_related = ("series",)


@admin.register(WindowStat)
class WindowStatAdmin(admin.ModelAdmin):
    list_display = ("series", "window", "min_value", "max_value", "sample_count", "computed_at")
    list_filter = ("window",)
    search_fields = ("series__storage_key",)
    list_select_related = ("series",)
