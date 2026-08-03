from django.urls import path

from bookkeeping import views


app_name = "bookkeeping"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("stammdaten/", views.StammdatenView.as_view(), name="stammdaten"),
    path("stammdaten/mandanten/<int:pk>/bearbeiten/", views.MandantUpdateView.as_view(), name="mandant_update"),
    path("stammdaten/bankkonten/", views.BankkontoListView.as_view(), name="bankkonto_list"),
    path("stammdaten/bankkonten/anlegen/", views.BankkontoCreateView.as_view(), name="bankkonto_create"),
    path("stammdaten/bankkonten/<int:pk>/bearbeiten/", views.BankkontoUpdateView.as_view(), name="bankkonto_update"),
    path("stammdaten/bankkonten/<int:pk>/loeschen/", views.BankkontoDeleteView.as_view(), name="bankkonto_delete"),
    path("stammdaten/kostenstellen/", views.KostenstelleListView.as_view(), name="kostenstelle_list"),
    path("stammdaten/kostenstellen/anlegen/", views.KostenstelleCreateView.as_view(), name="kostenstelle_create"),
    path("stammdaten/kostenstellen/<int:pk>/bearbeiten/", views.KostenstelleUpdateView.as_view(), name="kostenstelle_update"),
    path("stammdaten/kostenstellen/<int:pk>/loeschen/", views.KostenstelleDeleteView.as_view(), name="kostenstelle_delete"),
    path("stammdaten/kontenplaene/", views.KontenplanVersionListView.as_view(), name="kontenplanversion_list"),
    path("stammdaten/kontenplaene/importieren/", views.KontenplanImportView.as_view(), name="kontenplan_import"),
]
