from django.contrib import admin

from .models import (
    NavigationDimension,
    NavigationPlacement,
    NavigationProfile,
    NavigationProfileAction,
    NavigationProfileNavOrder,
    NavigationProfileOrder,
    NavigationStaticOption,
)


class NavigationProfileOrderInline(admin.TabularInline):
    model = NavigationProfileOrder
    extra = 0


class NavigationProfileNavOrderInline(admin.TabularInline):
    model = NavigationProfileNavOrder
    extra = 0


class NavigationProfileActionInline(admin.TabularInline):
    model = NavigationProfileAction
    extra = 0


@admin.register(NavigationDimension)
class NavigationDimensionAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "query_key", "enabled")
    list_filter = ("enabled", "query_key")
    search_fields = ("key", "label", "query_key")


@admin.register(NavigationProfile)
class NavigationProfileAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "enabled")
    list_filter = ("enabled",)
    search_fields = ("key", "label")
    inlines = (NavigationProfileOrderInline, NavigationProfileNavOrderInline, NavigationProfileActionInline)


@admin.register(NavigationPlacement)
class NavigationPlacementAdmin(admin.ModelAdmin):
    list_display = ("view_key", "profile", "enabled")
    list_filter = ("enabled", "profile")
    search_fields = ("view_key", "profile__key", "profile__label")


@admin.register(NavigationStaticOption)
class NavigationStaticOptionAdmin(admin.ModelAdmin):
    list_display = ("dimension", "value", "label", "sort_order", "enabled")
    list_filter = ("enabled", "dimension")
    search_fields = ("value", "label", "dimension__key")
