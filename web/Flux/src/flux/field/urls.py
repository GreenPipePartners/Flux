from django.urls import path

from . import views


app_name = "field"

urlpatterns = [
    path("", views.index, name="index"),
    path("config.json", views.config, name="config"),
]
