from django.views.generic import TemplateView
from .models import Property, Unit, Owner

class DashboardView(TemplateView):
    template_name = "webapp/home.html"

    def get_context_data(self, **kwargs):
        # Wir holen den Standard-Kontext
        context = super().get_context_data(**kwargs)
        
        # Wir zählen die Einträge für die Statistik-Kacheln
        context['stats'] = {
            'properties': Property.objects.count(),
            'units': Unit.objects.count(),
            'owners': Owner.objects.count(),
        }
        return context