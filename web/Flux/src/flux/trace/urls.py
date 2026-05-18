from django.urls import path

from . import views


app_name = "trace"

urlpatterns = [
    path("", views.index, name="index"),
    path("cache/<slug:profile_key>/", views.cache_profile, name="cache-profile"),
    path("cache/<slug:profile_key>/payload/", views.cache_profile_payload, name="cache-profile-payload"),
    path("wells/", views.nav_well_trace, name="nav-well-trace"),
    path("wells/payload/", views.nav_well_trace_payload, name="nav-well-trace-payload"),
    path("annotations/", views.annotations, name="annotations"),
    path("annotations/query/", views.query_annotations, name="query-annotations"),
    path("live/", views.live, name="live"),
    path("live/samples/", views.live_samples, name="live-samples"),
]
