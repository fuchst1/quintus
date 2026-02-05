from django.urls import reverse_lazy
from django.db import transaction
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.views.generic import DetailView
from .models import LeaseAgreement, Manager, Meter, MeterReading, Property, Unit, Owner, Tenant
from .forms import (
    LeaseAgreementForm,
    MeterForm,
    MeterReadingForm,
    PropertyForm,
    PropertyOwnershipFormSet,
    OwnerForm,
    UnitForm,
    ManagerForm,
    TenantForm,
)

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
    queryset = Property.objects.prefetch_related("ownerships__owner")

class PropertyCreateView(CreateView):
    model = Property
    form_class = PropertyForm # Statt 'fields = [...]'
    template_name = "webapp/property_form.html"
    success_url = reverse_lazy('property_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["ownership_formset"] = PropertyOwnershipFormSet(self.request.POST)
        else:
            context["ownership_formset"] = PropertyOwnershipFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        ownership_formset = context["ownership_formset"]
        if ownership_formset.is_valid():
            with transaction.atomic():
                self.object = form.save()
                ownership_formset.instance = self.object
                ownership_formset.save()
            return super().form_valid(form)
        return self.form_invalid(form)

class PropertyUpdateView(UpdateView):
    model = Property
    form_class = PropertyForm # Statt 'fields = [...]'
    template_name = "webapp/property_form.html"
    success_url = reverse_lazy('property_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["ownership_formset"] = PropertyOwnershipFormSet(
                self.request.POST,
                instance=self.object,
            )
        else:
            context["ownership_formset"] = PropertyOwnershipFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        ownership_formset = context["ownership_formset"]
        if ownership_formset.is_valid():
            with transaction.atomic():
                self.object = form.save()
                ownership_formset.instance = self.object
                ownership_formset.save()
            return super().form_valid(form)
        return self.form_invalid(form)

class PropertyDeleteView(DeleteView):
    model = Property
    template_name = "webapp/property_confirm_delete.html"
    success_url = reverse_lazy('property_list')


class OwnerListView(ListView):
    model = Owner
    template_name = "webapp/owner_list.html"
    context_object_name = "owners"


class OwnerCreateView(CreateView):
    model = Owner
    form_class = OwnerForm
    template_name = "webapp/owner_form.html"
    success_url = reverse_lazy("owner_list")


class OwnerUpdateView(UpdateView):
    model = Owner
    form_class = OwnerForm
    template_name = "webapp/owner_form.html"
    success_url = reverse_lazy("owner_list")


class OwnerDeleteView(DeleteView):
    model = Owner
    template_name = "webapp/owner_confirm_delete.html"
    success_url = reverse_lazy("owner_list")


class ManagerListView(ListView):
    model = Manager
    template_name = "webapp/manager_list.html"
    context_object_name = "managers"


class ManagerCreateView(CreateView):
    model = Manager
    form_class = ManagerForm
    template_name = "webapp/manager_form.html"
    success_url = reverse_lazy("manager_list")


class ManagerUpdateView(UpdateView):
    model = Manager
    form_class = ManagerForm
    template_name = "webapp/manager_form.html"
    success_url = reverse_lazy("manager_list")


class ManagerDeleteView(DeleteView):
    model = Manager
    template_name = "webapp/manager_confirm_delete.html"
    success_url = reverse_lazy("manager_list")


class TenantListView(ListView):
    model = Tenant
    template_name = "webapp/tenant_list.html"
    context_object_name = "tenants"


class TenantCreateView(CreateView):
    model = Tenant
    form_class = TenantForm
    template_name = "webapp/tenant_form.html"
    success_url = reverse_lazy("tenant_list")


class TenantUpdateView(UpdateView):
    model = Tenant
    form_class = TenantForm
    template_name = "webapp/tenant_form.html"
    success_url = reverse_lazy("tenant_list")


class TenantDeleteView(DeleteView):
    model = Tenant
    template_name = "webapp/tenant_confirm_delete.html"
    success_url = reverse_lazy("tenant_list")


class LeaseAgreementListView(ListView):
    model = LeaseAgreement
    template_name = "webapp/lease_list.html"
    context_object_name = "leases"
    queryset = LeaseAgreement.objects.select_related("unit", "manager").prefetch_related("tenants")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_leases"] = self.queryset.filter(status=LeaseAgreement.Status.AKTIV)
        context["ended_leases"] = self.queryset.filter(status=LeaseAgreement.Status.BEENDET)
        return context


class LeaseAgreementCreateView(CreateView):
    model = LeaseAgreement
    form_class = LeaseAgreementForm
    template_name = "webapp/lease_form.html"
    success_url = reverse_lazy("lease_list")


class LeaseAgreementUpdateView(UpdateView):
    model = LeaseAgreement
    form_class = LeaseAgreementForm
    template_name = "webapp/lease_form.html"
    success_url = reverse_lazy("lease_list")


class LeaseAgreementDeleteView(DeleteView):
    model = LeaseAgreement
    template_name = "webapp/lease_confirm_delete.html"
    success_url = reverse_lazy("lease_list")


class LeaseAgreementDetailView(DetailView):
    model = LeaseAgreement
    template_name = "webapp/lease_detail.html"
    context_object_name = "lease"


class MeterListView(ListView):
    model = Meter
    template_name = "webapp/meter_list.html"
    context_object_name = "meters"
    queryset = Meter.objects.select_related("property", "unit")


class MeterCreateView(CreateView):
    model = Meter
    form_class = MeterForm
    template_name = "webapp/meter_form.html"
    success_url = reverse_lazy("meter_list")


class MeterUpdateView(UpdateView):
    model = Meter
    form_class = MeterForm
    template_name = "webapp/meter_form.html"
    success_url = reverse_lazy("meter_list")


class MeterDeleteView(DeleteView):
    model = Meter
    template_name = "webapp/meter_confirm_delete.html"
    success_url = reverse_lazy("meter_list")


class MeterReadingListView(ListView):
    model = MeterReading
    template_name = "webapp/meter_reading_list.html"
    context_object_name = "readings"
    queryset = MeterReading.objects.select_related("meter")


class MeterReadingByMeterListView(ListView):
    model = MeterReading
    template_name = "webapp/meter_reading_by_meter_list.html"
    context_object_name = "readings"

    def get_queryset(self):
        return MeterReading.objects.select_related("meter", "meter__unit", "meter__property").filter(
            meter_id=self.kwargs["pk"]
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["meter"] = Meter.objects.select_related("unit", "property").get(pk=self.kwargs["pk"])
        return context


class MeterReadingCreateView(CreateView):
    model = MeterReading
    form_class = MeterReadingForm
    template_name = "webapp/meter_reading_form.html"
    success_url = reverse_lazy("meter_reading_list")

    def get_initial(self):
        initial = super().get_initial()
        meter_id = self.request.GET.get("meter")
        if meter_id and Meter.objects.filter(pk=meter_id).exists():
            initial["meter"] = meter_id
        return initial


class MeterReadingUpdateView(UpdateView):
    model = MeterReading
    form_class = MeterReadingForm
    template_name = "webapp/meter_reading_form.html"
    success_url = reverse_lazy("meter_reading_list")


class MeterReadingDeleteView(DeleteView):
    model = MeterReading
    template_name = "webapp/meter_reading_confirm_delete.html"
    success_url = reverse_lazy("meter_reading_list")


class UnitListView(ListView):
    model = Unit
    template_name = "webapp/unit_list.html"
    context_object_name = "units"
    queryset = Unit.objects.select_related("property").order_by("property__name", "door_number", "name")


class UnitCreateView(CreateView):
    model = Unit
    form_class = UnitForm
    template_name = "webapp/unit_form.html"
    success_url = reverse_lazy("unit_list")


class UnitUpdateView(UpdateView):
    model = Unit
    form_class = UnitForm
    template_name = "webapp/unit_form.html"
    success_url = reverse_lazy("unit_list")


class UnitDeleteView(DeleteView):
    model = Unit
    template_name = "webapp/unit_confirm_delete.html"
    success_url = reverse_lazy("unit_list")
