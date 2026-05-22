from django.urls import path

from . import views


app_name = "serve"

urlpatterns = [
    path("", views.index, name="index"),
    path("heartbeats/<int:heartbeat_id>/delete/", views.delete_heartbeat, name="delete_heartbeat"),
    path("heartbeats/delete-stale/", views.delete_stale_heartbeats, name="delete_stale_heartbeats"),
]
