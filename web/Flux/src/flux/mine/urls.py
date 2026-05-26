from django.urls import path

from . import views

app_name = "mine"

urlpatterns = [
    path("", views.index, name="index"),
    path("import/", views.import_source, name="import_source"),
]
