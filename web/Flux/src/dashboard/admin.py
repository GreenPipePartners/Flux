from django.contrib import admin

from .models import IgnitionBridgeConfig


@admin.register(IgnitionBridgeConfig)
class IgnitionBridgeConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "base_url", "last_test_ok", "last_test_at", "updated_at")
    list_filter = ("role", "last_test_ok")
    readonly_fields = ("last_test_ok", "last_test_message", "last_test_at", "updated_at")
