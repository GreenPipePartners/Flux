from django.urls import path

from . import views


app_name = "trace"

urlpatterns = [
    path("", views.index, name="index"),
    path("live/", views.live, name="live"),
    path("live/samples/", views.live_samples, name="live-samples"),
]
