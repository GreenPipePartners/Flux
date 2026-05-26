from django.urls import path
from django.views.generic import RedirectView

from flux.chart import views


urlpatterns = [
    path("", views.index, name="index"),
    path("cache/<slug:profile_key>/", views.cache_profile, name="cache-profile"),
    path("cache/<slug:profile_key>/payload/", views.cache_profile_payload, name="cache-profile-payload"),
    path("wells/", views.nav_well_trace, name="nav-well-trace"),
    path("wells/embed/", views.nav_well_trace_embed, name="nav-well-trace-embed"),
    path("wells/payload/", views.nav_well_trace_payload, name="nav-well-trace-payload"),
    path("annotations/", views.annotations, name="annotations"),
    path("annotations/query/", views.query_annotations, name="query-annotations"),
    path("demand/", views.demand, name="demand"),
    path("stream/", views.stream, name="stream"),
    path("stream/samples/", views.stream_samples, name="stream-samples"),
    path("live/samples/", RedirectView.as_view(url="/chart/stream/samples/", permanent=True, query_string=True)),
    path("live/", RedirectView.as_view(url="/chart/stream/", permanent=True, query_string=True)),
    path("fluxolot/", views.fluxolot_trace, name="fluxolot-trace"),
    path("fluxolot/payload/", views.fluxolot_trace_payload, name="fluxolot-trace-payload"),
    path("<slug:scope>/", views.scope_profile, name="scope-profile"),
    path("<slug:scope>/payload/", views.scope_profile_payload, name="scope-profile-payload"),
]
