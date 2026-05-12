from django.urls import path

from . import views


app_name = "opt"

urlpatterns = [path("", views.index, name="index")]
