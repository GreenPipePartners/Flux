"""Flux Chart admin registrations will be added as chart-specific models are introduced."""
from django.contrib import admin

from .models import TraceAnnotation, TraceAnnotationTarget, TraceCacheCursor, TraceProfile, TraceSignal


class TraceSignalInline(admin.TabularInline):
    model = TraceSignal
    extra = 0
    fields = ("tag", "label", "axis_key", "axis_label", "unit", "sort_order", "default_visible", "cache_enabled")


@admin.register(TraceProfile)
class TraceProfileAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "enabled", "cache_enabled", "cache_window_minutes", "sync_interval_seconds")
    search_fields = ("key", "label")
    inlines = [TraceSignalInline]


@admin.register(TraceSignal)
class TraceSignalAdmin(admin.ModelAdmin):
    list_display = ("profile", "display_label", "tag", "axis_key", "sort_order", "cache_enabled")
    list_filter = ("profile", "axis_key", "cache_enabled", "default_visible")
    search_fields = ("label", "tag__display_name", "tag__path")


@admin.register(TraceCacheCursor)
class TraceCacheCursorAdmin(admin.ModelAdmin):
    list_display = ("signal", "last_timestamp", "last_sync_at", "last_error")
    search_fields = ("signal__label", "signal__tag__path")


class TraceAnnotationTargetInline(admin.TabularInline):
    model = TraceAnnotationTarget
    extra = 0
    fields = ("signal", "historian_path", "ignition_storage_id", "quality_code")


@admin.register(TraceAnnotation)
class TraceAnnotationAdmin(admin.ModelAdmin):
    list_display = ("marker_time", "profile", "marker_id", "text", "source")
    list_filter = ("profile", "source")
    search_fields = ("text", "targets__historian_path", "targets__ignition_storage_id")
    inlines = [TraceAnnotationTargetInline]
