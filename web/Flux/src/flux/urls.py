from django.views.generic import RedirectView
from django.urls import include, path


urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url="/static/flux/favicon.svg", permanent=True)),
    path("serve/", include("flux.serve.urls")),
    path("mine/", include("flux.mine.urls")),
    path("build/", include("flux.build.urls")),
    path("cell/", include("flux.cell.urls")),
    path("sim/", include("flux.sim.urls")),
    path("spot/", include("flux.spot.urls")),
    path("live/<path:remaining>", RedirectView.as_view(url="/spot/%(remaining)s", permanent=True, query_string=True)),
    path("live/", RedirectView.as_view(url="/spot/", permanent=True, query_string=True)),
    path("chart/", include("flux.chart.urls")),
    path("charts/<path:remaining>", RedirectView.as_view(url="/chart/%(remaining)s", permanent=True, query_string=True)),
    path("charts/", RedirectView.as_view(url="/chart/", permanent=True, query_string=True)),
    path("trace/<path:remaining>", RedirectView.as_view(url="/chart/%(remaining)s", permanent=False, query_string=True)),
    path("trace/", RedirectView.as_view(url="/chart/", permanent=False, query_string=True)),
    path("trace-clone/live/samples/", RedirectView.as_view(pattern_name="chart:stream-samples", permanent=False, query_string=True)),
    path("trace-clone/live/", RedirectView.as_view(pattern_name="chart:stream", permanent=False, query_string=True)),
    path("trace-clone/", RedirectView.as_view(pattern_name="chart:index", permanent=False, query_string=True)),
    path("", include("dashboard.urls")),
]
