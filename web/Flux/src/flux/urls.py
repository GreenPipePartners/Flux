from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("serve/", include("flux.serve.urls")),
    path("opt/", include("flux.opt.urls")),
    path("sim/", include("flux.sim.urls")),
    path("field/", include("flux.field.urls")),
    path("nav/", include("flux.nav.urls")),
    path("live/", include("flux.live.urls")),
    path("trace/", include("flux.trace.urls")),
    path("", include("dashboard.urls")),
]
