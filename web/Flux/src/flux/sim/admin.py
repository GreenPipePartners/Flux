from django.contrib import admin

from .models import SimHistoryBackfill, SimSchedule, SimTag


@admin.register(SimSchedule)
class SimScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "interval_seconds", "enabled")
    list_filter = ("enabled",)
    search_fields = ("name", "description")


@admin.register(SimTag)
class SimTagAdmin(admin.ModelAdmin):
    list_display = ("name", "data_type", "pattern", "schedule", "tag_path", "enabled", "last_value")
    list_filter = ("enabled", "data_type", "pattern", "schedule", "provider")
    search_fields = ("provider", "folder_path", "name", "display_name")


@admin.register(SimHistoryBackfill)
class SimHistoryBackfillAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "start_at", "duration_days", "interval_seconds", "completed_at")
    list_filter = ("status",)
    search_fields = ("name", "history_prefix", "last_error")
