from django.contrib import admin

from .models import DailyTagExtreme, LatestTagValue, RuntimeSchedulerConfig, RuntimeTag, TagSample, TagSchedule


@admin.register(TagSchedule)
class TagScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "interval_seconds", "enabled")
    list_filter = ("enabled",)


@admin.register(RuntimeTag)
class RuntimeTagAdmin(admin.ModelAdmin):
    list_display = ("display_name", "asset_name", "provider", "path", "schedule", "balancer_code", "enabled")
    list_filter = ("enabled", "schedule", "provider", "balancer_code")
    search_fields = ("display_name", "asset_name", "provider", "path")


@admin.register(RuntimeSchedulerConfig)
class RuntimeSchedulerConfigAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "hot_interval_seconds",
        "warm_interval_seconds",
        "warm_cycles_after_hot",
        "cold_bucket_count",
        "current_balancer_code",
        "balancer_increment",
        "demand_lease_seconds",
        "enabled",
        "updated_at",
    )
    list_filter = ("enabled",)


@admin.register(LatestTagValue)
class LatestTagValueAdmin(admin.ModelAdmin):
    list_display = ("tag", "tag_schedule", "value", "quality_code", "value_timestamp", "read_at", "updated_at")
    list_filter = ("quality_code", "tag__schedule")
    list_select_related = ("tag", "tag__schedule")
    search_fields = ("tag__display_name", "tag__asset_name", "tag__path")

    @admin.display(description="Schedule", ordering="tag__schedule__interval_seconds")
    def tag_schedule(self, obj):
        return obj.tag.schedule


@admin.register(TagSample)
class TagSampleAdmin(admin.ModelAdmin):
    list_display = ("tag", "tag_schedule", "value", "quality_code", "value_timestamp", "read_at")
    list_filter = ("quality_code", "tag__schedule")
    list_select_related = ("tag", "tag__schedule")
    search_fields = ("tag__display_name", "tag__asset_name", "tag__path")

    @admin.display(description="Schedule", ordering="tag__schedule__interval_seconds")
    def tag_schedule(self, obj):
        return obj.tag.schedule


@admin.register(DailyTagExtreme)
class DailyTagExtremeAdmin(admin.ModelAdmin):
    list_display = ("tag", "date", "min_value", "max_value", "sample_count", "updated_at")
    list_filter = ("date", "tag__schedule")
    list_select_related = ("tag", "tag__schedule")
    search_fields = ("tag__display_name", "tag__asset_name", "tag__path")
