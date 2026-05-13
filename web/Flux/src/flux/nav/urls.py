from django.urls import path

from . import views


app_name = "nav"

urlpatterns = [
    path("", views.index, name="index"),
]
