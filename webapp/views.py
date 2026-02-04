from django.urls import reverse_lazy
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from .models import Property, Unit, Owner
from .forms import PropertyForm

# Bestehendes Dashboard
class DashboardView(TemplateView):
    template_name = "webapp/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stats'] = {
            'properties': Property.objects.count(),
            'units': Unit.objects.count(),
            'owners': Owner.objects.count(),
        }
        return context

# NEU: CRUD Views für Liegenschaften
class PropertyListView(ListView):
    model = Property
    template_name = "webapp/property_list.html"
    context_object_name = "properties"

class PropertyCreateView(CreateView):
    model = Property
    form_class = PropertyForm # Statt 'fields = [...]'
    template_name = "webapp/property_form.html"
    success_url = reverse_lazy('property_list')

class PropertyUpdateView(UpdateView):
    model = Property
    form_class = PropertyForm # Statt 'fields = [...]'
    template_name = "webapp/property_form.html"
    success_url = reverse_lazy('property_list')

class PropertyDeleteView(DeleteView):
    model = Property
    template_name = "webapp/property_confirm_delete.html"
    success_url = reverse_lazy('property_list')