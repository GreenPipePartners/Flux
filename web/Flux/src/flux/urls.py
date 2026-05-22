from django.contrib import admin
from django.views.generic import RedirectView
from django.urls import include, path


urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url="/static/flux/favicon.svg", permanent=True)),
    path("admin/", admin.site.urls),
    path("field/", include("flux.field.urls")),
    path("serve/", include("flux.serve.urls")),
    path("sim/", include("flux.sim.urls")),
    path("live/", include("flux.live.urls")),
    path("trace/", include("flux.trace.urls")),
    path("trace-clone/live/samples/", RedirectView.as_view(pattern_name="trace:live-samples", permanent=False)),
    path("trace-clone/live/", RedirectView.as_view(pattern_name="trace:live", permanent=False)),
    path("trace-clone/", RedirectView.as_view(pattern_name="trace:index", permanent=False)),
    path("", include("dashboard.urls")),
]
