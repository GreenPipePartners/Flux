from django.urls import path

from . import views

app_name = "build"

urlpatterns = [
    path("", views.index, name="index"),
    path("seed-hmi-demo/", views.seed_hmi_demo, name="seed_hmi_demo"),
    path("hmi-map/build/", views.build_hmi_map, name="build_hmi_map"),
]
