from django.urls import path

from . import views


app_name = "live"

urlpatterns = [
    path("", views.index, name="index"),
    path("pad-overview/", views.pad_overview, name="pad_overview"),
    path("pad-overview/panel/", views.pad_overview_tab_panel, name="pad_overview_tab_panel"),
    path("pad-overview/cards/", views.pad_overview_cards_partial, name="pad_overview_cards"),
]
