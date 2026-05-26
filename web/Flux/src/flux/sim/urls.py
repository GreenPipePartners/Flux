from django.urls import path

from . import views


app_name = "sim"

urlpatterns = [
    path("", views.index, name="index"),
    path("import/json/", views.import_provider_json, name="import_provider_json"),
    path("import/ignition/", views.import_provider_ignition, name="import_provider_ignition"),
    path("remove-ignition-tags/", views.remove_ignition_sim_tags, name="remove_ignition_sim_tags"),
    path("apply-selection/", views.apply_selection, name="apply_selection"),
    path("imported/set-enabled/", views.set_imported_enabled, name="set_imported_enabled"),
    path("imported/set-bulk/", views.set_imported_bulk, name="set_imported_bulk"),
    path("imported/tree/children/", views.provider_tree_children, name="provider_tree_children"),
    path("imported/selected-paths.json", views.selected_paths, name="selected_paths"),
    path("jobs/status/", views.job_status, name="job_status"),
    path("field-config.json", views.field_config, name="field_config"),
]
