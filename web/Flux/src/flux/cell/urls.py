from django.urls import path

from . import views

app_name = "cell"

urlpatterns = [
    path("", views.index, name="index"),
    path("phone-demo/", views.phone_demo, name="phone_demo"),
    path("import/", views.import_bundle, name="import_bundle"),
    path("seed-demo/", views.seed_demo, name="seed_demo"),
    path("bundles/<slug:bundle_key>/cells/<slug:cell_slug>/comments/", views.add_comment, name="add_comment"),
    path("api/bundles/<slug:bundle_key>/cells.csv", views.cells_csv, name="cells_csv"),
    path("api/bundles/<slug:bundle_key>/points.csv", views.points_csv, name="points_csv"),
    path("api/bundles/<slug:bundle_key>/relationships.csv", views.relationships_csv, name="relationships_csv"),
    path("api/bundles/<slug:bundle_key>/visuals.csv", views.visuals_csv, name="visuals_csv"),
    path("api/bundles/<slug:bundle_key>/sources.csv", views.sources_csv, name="sources_csv"),
    path("api/bundles/<slug:bundle_key>/live-scope.csv", views.live_scope_csv, name="live_scope_csv"),
    path("api/bundles/<slug:bundle_key>/trace-scopes.csv", views.trace_scopes_csv, name="trace_scopes_csv"),
]
