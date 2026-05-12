from django.contrib import admin

from .models import BrowseNode, OptimizationLease, OptimizedTagPath, RefreshLane


@admin.register(RefreshLane)
class RefreshLaneAdmin(admin.ModelAdmin):
    list_display = ("name", "interval_seconds", "priority", "max_batch_size", "enabled")
    list_filter = ("enabled",)


@admin.register(OptimizedTagPath)
class OptimizedTagPathAdmin(admin.ModelAdmin):
    list_display = ("full_path", "lane", "enabled", "next_due_at", "failure_count")
    list_filter = ("enabled", "lane")
    search_fields = ("provider", "path", "full_path")


@admin.register(BrowseNode)
class BrowseNodeAdmin(admin.ModelAdmin):
    list_display = ("provider", "path", "has_children", "next_due_at", "cold_score")
    list_filter = ("provider", "has_children")
    search_fields = ("provider", "path", "parent_path")


@admin.register(OptimizationLease)
class OptimizationLeaseAdmin(admin.ModelAdmin):
    list_display = ("work_type", "target_path", "claimed_by", "expires_at", "completed_at")
    list_filter = ("work_type",)
    search_fields = ("target_path", "claimed_by")
