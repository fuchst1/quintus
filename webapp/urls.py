
from django.urls import path
from .views import DashboardView, PropertyListView, PropertyCreateView, PropertyUpdateView, PropertyDeleteView

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('properties/', PropertyListView.as_view(), name='property_list'),
    path('properties/add/', PropertyCreateView.as_view(), name='property_create'),
    path('properties/<int:pk>/edit/', PropertyUpdateView.as_view(), name='property_update'),
    path('properties/<int:pk>/delete/', PropertyDeleteView.as_view(), name='property_delete'),
]