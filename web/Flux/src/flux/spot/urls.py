from django.urls import path

from flux.spot import views


app_name = "spot"

urlpatterns = [
    path("", views.index, name="index"),
    path("pad-overview/", views.pad_overview, name="pad_overview"),
    path("pad-overview/panel/", views.pad_overview_tab_panel, name="pad_overview_tab_panel"),
    path("pad-overview/cards/", views.pad_overview_cards_partial, name="pad_overview_cards"),
    path("<slug:scope>/", views.scope_detail, name="scope_detail"),
    path("<slug:scope>/panel/", views.scope_tab_panel, name="scope_panel"),
    path("<slug:scope>/cards/", views.scope_cards_partial, name="scope_cards"),
]
