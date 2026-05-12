from django.urls import path

from . import views


app_name = "sim"

urlpatterns = [path("", views.index, name="index")]
