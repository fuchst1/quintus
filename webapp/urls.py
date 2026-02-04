from django.urls import path
from .views import DashboardView

urlpatterns = [
    # Der leere Pfad '' ist die Homepage der App
    path('', DashboardView.as_view(), name='dashboard'),
]