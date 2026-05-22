from __future__ import annotations

from .filter import NavigationFilter
from .models import NavigationProfile
from .views import cleared_filter_keys, first_filter_dimension, first_nav_dimension, filters_from_request, profile_for_category, profile_order


def navigation_context(request, *, default_profile_key: str = "well") -> dict:
    clear_key = request.GET.get("clear")
    category = clear_key or request.GET.get("changed")
    display_profile = selected_display_profile(request, default_profile_key=default_profile_key)
    if display_profile is None:
        return {
            "profiles": NavigationProfile.objects.none(),
            "selected_profile": None,
            "action_profile": None,
            "changed": category,
            "display_order": [],
            "result": None,
        }
    category = category or first_nav_dimension(display_profile) or first_filter_dimension(display_profile)
    action_profile = profile_for_category(category) or display_profile
    filters = filters_from_request(request)
    suppress_define = cleared_filter_keys(request)
    if clear_key in filters:
        filters[clear_key] = None
    result = NavigationFilter(action_profile, filters, category, suppress_define=suppress_define).resolve()
    return {
        "profiles": NavigationProfile.objects.filter(enabled=True),
        "selected_profile": display_profile,
        "action_profile": action_profile,
        "changed": category,
        "display_order": profile_order(display_profile),
        "result": result,
    }


def selected_display_profile(request, *, default_profile_key: str):
    key = request.GET.get("profile", default_profile_key)
    return (
        NavigationProfile.objects.filter(key=key, enabled=True).first()
        or NavigationProfile.objects.filter(enabled=True).order_by("key").first()
    )
