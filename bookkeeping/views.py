from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from bookkeeping.forms import BankkontoForm, KontenplanImportForm, KostenstelleForm, MandantForm
from bookkeeping.models import AuditEreignis, Bankkonto, KontenplanVersion, Kostenstelle, Mandant
from bookkeeping.services.audit import record_audit_event


class DashboardView(TemplateView):
    template_name = "bookkeeping/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "mandanten": Mandant.objects.filter(aktiv=True).order_by("name"),
                "bankkonto_count": Bankkonto.objects.count(),
                "kostenstelle_count": Kostenstelle.objects.count(),
                "aktive_kontenplaene": KontenplanVersion.objects.filter(aktiv=True).select_related("mandant"),
                "audit_ereignisse": AuditEreignis.objects.select_related("mandant", "benutzer")[:8],
            }
        )
        return context


class StammdatenView(TemplateView):
    template_name = "bookkeeping/masterdata/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "mandanten": Mandant.objects.order_by("name"),
                "bankkonten": Bankkonto.objects.select_related("mandant").order_by("mandant__name", "bezeichnung"),
                "kostenstellen": Kostenstelle.objects.select_related("mandant").order_by("mandant__name", "code"),
                "kontenplaene": KontenplanVersion.objects.select_related("mandant").order_by("mandant__name", "-gueltig_ab"),
            }
        )
        return context


class MandantUpdateView(UpdateView):
    model = Mandant
    form_class = MandantForm
    template_name = "bookkeeping/masterdata/form.html"
    success_url = reverse_lazy("bookkeeping:stammdaten")

    def form_valid(self, form):
        response = super().form_valid(form)
        record_audit_event(
            mandant=self.object,
            objekt_typ="Mandant",
            objekt_id=self.object.pk,
            aktion="mandant_aktualisiert",
            nachher={"name": self.object.name, "kurzname": self.object.kurzname},
            user=self.request.user,
        )
        messages.success(self.request, "Mandant wurde gespeichert.")
        return response


class BankkontoListView(ListView):
    model = Bankkonto
    template_name = "bookkeeping/masterdata/bankkonto_list.html"
    context_object_name = "bankkonten"

    def get_queryset(self):
        return Bankkonto.objects.select_related("mandant").order_by("mandant__name", "bezeichnung")


class BankkontoCreateView(CreateView):
    model = Bankkonto
    form_class = BankkontoForm
    template_name = "bookkeeping/masterdata/form.html"
    success_url = reverse_lazy("bookkeeping:bankkonto_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        record_audit_event(
            mandant=self.object.mandant,
            objekt_typ="Bankkonto",
            objekt_id=self.object.pk,
            aktion="bankkonto_erstellt",
            nachher={"iban": self.object.iban_normalisiert, "bezeichnung": self.object.bezeichnung},
            user=self.request.user,
        )
        messages.success(self.request, "Bankkonto wurde angelegt.")
        return response


class BankkontoUpdateView(UpdateView):
    model = Bankkonto
    form_class = BankkontoForm
    template_name = "bookkeeping/masterdata/form.html"
    success_url = reverse_lazy("bookkeeping:bankkonto_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        record_audit_event(
            mandant=self.object.mandant,
            objekt_typ="Bankkonto",
            objekt_id=self.object.pk,
            aktion="bankkonto_aktualisiert",
            nachher={"iban": self.object.iban_normalisiert, "bezeichnung": self.object.bezeichnung},
            user=self.request.user,
        )
        messages.success(self.request, "Bankkonto wurde gespeichert.")
        return response


class BankkontoDeleteView(DeleteView):
    model = Bankkonto
    template_name = "bookkeeping/masterdata/confirm_delete.html"
    success_url = reverse_lazy("bookkeeping:bankkonto_list")

    def form_valid(self, form):
        object_to_delete = self.get_object()
        mandant = object_to_delete.mandant
        object_id = object_to_delete.pk
        response = super().form_valid(form)
        record_audit_event(
            mandant=mandant,
            objekt_typ="Bankkonto",
            objekt_id=object_id,
            aktion="bankkonto_geloescht",
            user=self.request.user,
        )
        messages.success(self.request, "Bankkonto wurde gelöscht.")
        return response


class KostenstelleListView(ListView):
    model = Kostenstelle
    template_name = "bookkeeping/masterdata/kostenstelle_list.html"
    context_object_name = "kostenstellen"

    def get_queryset(self):
        return Kostenstelle.objects.select_related("mandant").order_by("mandant__name", "code")


class KostenstelleCreateView(CreateView):
    model = Kostenstelle
    form_class = KostenstelleForm
    template_name = "bookkeeping/masterdata/form.html"
    success_url = reverse_lazy("bookkeeping:kostenstelle_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        record_audit_event(
            mandant=self.object.mandant,
            objekt_typ="Kostenstelle",
            objekt_id=self.object.pk,
            aktion="kostenstelle_erstellt",
            nachher={"code": self.object.code, "bezeichnung": self.object.bezeichnung},
            user=self.request.user,
        )
        messages.success(self.request, "Kostenstelle wurde angelegt.")
        return response


class KostenstelleUpdateView(UpdateView):
    model = Kostenstelle
    form_class = KostenstelleForm
    template_name = "bookkeeping/masterdata/form.html"
    success_url = reverse_lazy("bookkeeping:kostenstelle_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        record_audit_event(
            mandant=self.object.mandant,
            objekt_typ="Kostenstelle",
            objekt_id=self.object.pk,
            aktion="kostenstelle_aktualisiert",
            nachher={"code": self.object.code, "bezeichnung": self.object.bezeichnung},
            user=self.request.user,
        )
        messages.success(self.request, "Kostenstelle wurde gespeichert.")
        return response


class KostenstelleDeleteView(DeleteView):
    model = Kostenstelle
    template_name = "bookkeeping/masterdata/confirm_delete.html"
    success_url = reverse_lazy("bookkeeping:kostenstelle_list")

    def form_valid(self, form):
        object_to_delete = self.get_object()
        mandant = object_to_delete.mandant
        object_id = object_to_delete.pk
        response = super().form_valid(form)
        record_audit_event(
            mandant=mandant,
            objekt_typ="Kostenstelle",
            objekt_id=object_id,
            aktion="kostenstelle_geloescht",
            user=self.request.user,
        )
        messages.success(self.request, "Kostenstelle wurde gelöscht.")
        return response


class KontenplanVersionListView(ListView):
    model = KontenplanVersion
    template_name = "bookkeeping/masterdata/kontenplanversion_list.html"
    context_object_name = "kontenplaene"

    def get_queryset(self):
        return KontenplanVersion.objects.select_related("mandant").prefetch_related("eintraege").order_by(
            "mandant__name", "-gueltig_ab"
        )


class KontenplanImportView(TemplateView):
    template_name = "bookkeeping/masterdata/kontenplan_import.html"

    def get(self, request, *args, **kwargs):
        return self.render_to_response({"form": KontenplanImportForm()})

    def post(self, request, *args, **kwargs):
        form = KontenplanImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response({"form": form})
        version = form.save(user=request.user)
        if version is None:
            return self.render_to_response({"form": form})
        messages.success(request, f"Kontenplan mit {version.eintraege.count()} Kategorien wurde importiert.")
        return redirect("bookkeeping:kontenplanversion_list")
