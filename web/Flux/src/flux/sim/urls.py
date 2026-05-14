from django.urls import path

from . import views


app_name = "sim"

urlpatterns = [
    path("", views.index, name="index"),
    path("set-enabled/", views.set_enabled, name="set_enabled"),
    path("import/json/", views.import_provider_json, name="import_provider_json"),
    path("import/ignition/", views.import_provider_ignition, name="import_provider_ignition"),
    path("remove-ignition-tags/", views.remove_ignition_sim_tags, name="remove_ignition_sim_tags"),
    path("imported/set-enabled/", views.set_imported_enabled, name="set_imported_enabled"),
    path("imported/set-bulk/", views.set_imported_bulk, name="set_imported_bulk"),
    path("imported/selected-paths.json", views.selected_paths, name="selected_paths"),
]
