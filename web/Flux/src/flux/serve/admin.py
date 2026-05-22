from django.contrib import admin

from .models import ServeCommand, ServeHeartbeat, ServeServiceSnapshot


@admin.register(ServeHeartbeat)
class ServeHeartbeatAdmin(admin.ModelAdmin):
    list_display = ("service_name", "instance_id", "platform", "status", "last_seen_at", "pid")
    list_filter = ("platform", "status", "service_name")
    search_fields = ("service_name", "instance_id", "current_job", "last_error")


@admin.register(ServeCommand)
class ServeCommandAdmin(admin.ModelAdmin):
    list_display = ("command", "status", "requested_by", "requested_at", "completed_at")
    list_filter = ("status", "command")
    search_fields = ("command", "error")


@admin.register(ServeServiceSnapshot)
class ServeServiceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("service_key", "category", "desired_state", "observed_state", "severity", "last_checked_at")
    list_filter = ("category", "desired_state", "observed_state", "severity")
    search_fields = ("service_key", "display_name", "summary", "last_error")
