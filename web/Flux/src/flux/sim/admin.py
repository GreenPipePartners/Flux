from django.contrib import admin

from .models import SimProviderSelection


@admin.register(SimProviderSelection)
class SimProviderSelectionAdmin(admin.ModelAdmin):
    list_display = ("provider", "path", "enabled", "updated_at")
    list_filter = ("enabled", "provider")
    search_fields = ("provider", "path")
