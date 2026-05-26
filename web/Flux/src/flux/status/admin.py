from django.contrib import admin

from .models import LatestStatus


@admin.register(LatestStatus)
class LatestStatusAdmin(admin.ModelAdmin):
    list_display = ("entity", "status_kind", "observed_state", "severity", "source", "source_instance", "last_seen_at")
    list_filter = ("status_kind", "observed_state", "severity", "source")
    search_fields = ("entity__natural_key", "entity__display_name", "summary", "detail", "source_instance")
    list_select_related = ("entity",)
