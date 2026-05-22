from django.urls import path

from . import views


app_name = "dashboard"

urlpatterns = [
    path("setup/", views.setup, name="setup"),
    path("bridges/", views.bridges, name="bridges"),
    path("", views.home, name="home"),
]
