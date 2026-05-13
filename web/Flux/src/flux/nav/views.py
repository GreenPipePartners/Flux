from django.shortcuts import get_object_or_404, render

from .filter import NavigationFilter
from .models import NavigationDimension, NavigationProfile
from .registry import run_navigation_query


CLEAR_VALUE = "-- clear --"


def index(request):
    clear_key = request.GET.get("clear")
    category = clear_key or request.GET.get("changed")
    display_profile = selected_profile(request)
    category = category or first_nav_dimension(display_profile) or first_filter_dimension(display_profile)
    action_profile = profile_for_category(category) or display_profile
    filters = filters_from_request(request)
    suppress_define = cleared_filter_keys(request)
    if clear_key in filters:
        filters[clear_key] = None
    nav_filter = NavigationFilter(action_profile, filters, category, suppress_define=suppress_define)
    result = nav_filter.resolve()
    context = {
        "profiles": NavigationProfile.objects.filter(enabled=True),
        "selected_profile": display_profile,
        "action_profile": action_profile,
        "changed": category,
        "display_order": profile_order(display_profile),
        "result": result,
    }
    if request.headers.get("HX-Request"):
        return render(request, "nav/partials/navigation_panel.html", context)
    return render(request, "nav/index.html", context)


def selected_profile(request):
    key = request.GET.get("profile", "well")
    return get_object_or_404(NavigationProfile, key=key, enabled=True)


def profile_for_category(category: str | None):
    if not category:
        return None
    return NavigationProfile.objects.filter(key=category, enabled=True).first()


def filters_from_request(request) -> dict[str, str | None]:
    dimensions = {dimension.key: dimension for dimension in NavigationDimension.objects.filter(enabled=True)}
    filters = {key: parsed_value(request.GET.get(key)) for key in dimensions}
    for key, dimension in dimensions.items():
        filters[key] = resolve_option_value(dimension, request.GET.get(key), filters)
    return filters


def cleared_filter_keys(request) -> set[str]:
    keys = set()
    clear_key = request.GET.get("clear")
    if clear_key:
        keys.add(clear_key)
    for key in NavigationDimension.objects.filter(enabled=True).values_list("key", flat=True):
        if request.GET.get(key) == CLEAR_VALUE:
            keys.add(key)
    return keys


def parsed_value(value: str | None) -> str | None:
    if value in (None, "", "None", CLEAR_VALUE):
        return None
    if ":" in value:
        return value.split(":", 1)[0].strip() or None
    return value.strip()


def resolve_option_value(dimension: NavigationDimension, raw_value: str | None, filters: dict[str, str | None]) -> str | None:
    value = parsed_value(raw_value)
    if value is None:
        return None
    if raw_value and ":" in raw_value:
        return value
    query_filters = filters.copy()
    query_filters[dimension.key] = None
    for option in run_navigation_query(dimension, query_filters):
        if option.value == value or option.label.lower() == value.lower():
            return option.value
    return value


def first_filter_dimension(profile):
    row = profile.filter_order.select_related("dimension").order_by("position").first()
    return row.dimension.key if row else None


def profile_order(profile):
    return list(profile.filter_order.select_related("dimension").order_by("position").values_list("dimension__key", flat=True))


def first_nav_dimension(profile):
    row = profile.nav_order.select_related("dimension").order_by("position").first()
    return row.dimension.key if row else None
