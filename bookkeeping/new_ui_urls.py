"""Routes for the Core Ledger component system and its reference pages."""

from django.urls import path

from .ui_components import ComponentShowcaseView


app_name = "bookkeeping_new_ui"


urlpatterns = [
    path("components/", ComponentShowcaseView.as_view(), name="components"),
]
