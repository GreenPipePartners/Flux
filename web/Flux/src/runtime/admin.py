from django.contrib import admin

from .models import LatestTagValue, RuntimeTag, TagSample, TagSchedule


@admin.register(TagSchedule)
class TagScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "interval_seconds", "enabled")
    list_filter = ("enabled",)


@admin.register(RuntimeTag)
class RuntimeTagAdmin(admin.ModelAdmin):
    list_display = ("display_name", "asset_name", "provider", "path", "schedule", "enabled")
    list_filter = ("enabled", "schedule", "provider")
    search_fields = ("display_name", "asset_name", "provider", "path")


@admin.register(LatestTagValue)
class LatestTagValueAdmin(admin.ModelAdmin):
    list_display = ("tag", "value", "quality_code", "value_timestamp", "read_at")
    list_filter = ("quality_code",)
    search_fields = ("tag__display_name", "tag__asset_name", "tag__path")


@admin.register(TagSample)
class TagSampleAdmin(admin.ModelAdmin):
    list_display = ("tag", "value", "quality_code", "value_timestamp", "read_at")
    list_filter = ("quality_code",)
    search_fields = ("tag__display_name", "tag__asset_name", "tag__path")
