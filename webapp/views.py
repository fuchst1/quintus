import json
import os
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from itertools import combinations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpResponse
from django.db.models import Count, DecimalField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.views.generic import DetailView, View
from .models import (
    Abrechnungslauf,
    Abrechnungsschreiben,
    BetriebskostenBeleg,
    BetriebskostenGruppe,
    Buchung,
    Datei,
    LeaseAgreement,
    Manager,
    Meter,
    MeterReading,
    Owner,
    Property,
    Tenant,
    Unit,
    ReminderRuleConfig,
    VpiAdjustmentLetter,
    VpiAdjustmentRun,
    VpiIndexValue,
)
from .forms import (
    BankImportForm,
    BetriebskostenBelegForm,
    BetriebskostenGruppeForm,
    BuchungForm,
    DateiUploadForm,
    LeaseAgreementForm,
    MeterForm,
    MeterReadingForm,
    PropertyForm,
    PropertyOwnershipFormSet,
    ReminderRuleConfigFormSet,
    VpiIndexValueFormSet,
    OwnerForm,
    UnitForm,
    ManagerForm,
    TenantForm,
)
from .services.files import DateiService
from .services.annual_statement_pdf_service import AnnualStatementPdfService
from .services.annual_statement_run_service import AnnualStatementRunService
from .services.operating_cost_service import OperatingCostService
from .services.settlement_adjustments import match_settlement_adjustment_text
from .services.reminders import ReminderService
from .services.vpi_adjustment_pdf_service import VpiAdjustmentPdfService
from .services.vpi_adjustment_run_service import VpiAdjustmentRunService


def build_attachments_panel_context(request, target_object, *, title: str):
    selected_filter = DateiService.normalize_filter_key(request.GET.get("datei_filter"))
    assignments = DateiService.list_assignments_for_object(
        target_object=target_object,
        filter_key=selected_filter,
        include_archived=False,
    )
    rows = []
    for assignment in assignments:
        datei = assignment.datei
        if datei is None:
            continue
        mime_type = (datei.mime_type or "").lower()
        is_image = mime_type.startswith("image/") or datei.kategorie in {
            Datei.Kategorie.BILD,
            Datei.Kategorie.ZAEHLERFOTO,
        }
        rows.append(
            {
                "assignment": assignment,
                "datei": datei,
                "is_image": is_image,
                "can_download": DateiService.can_download(user=None, datei=datei),
                "can_archive": DateiService.can_archive(user=None, datei=datei),
            }
        )

    filters = []
    for item in DateiService.filter_definitions():
        filters.append(
            {
                "key": item["key"],
                "label": item["label"],
                "active": item["key"] == selected_filter,
                "url": f"{request.path}?datei_filter={item['key']}",
            }
        )

    return {
        "title": title,
        "target_app_label": target_object._meta.app_label,
        "target_model": target_object._meta.model_name,
        "target_object_id": target_object.pk,
        "category_choices": DateiService.category_choices(),
        "rows": rows,
        "filters": filters,
        "selected_filter": selected_filter,
        "can_upload": DateiService.can_upload(target_object=target_object),
        "next_url": request.get_full_path(),
    }

# Bestehendes Dashboard
class DashboardView(TemplateView):
    template_name = "webapp/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        active_leases = LeaseAgreement.objects.filter(status=LeaseAgreement.Status.AKTIV)

        stats = {
            "properties": Property.objects.count(),
            "units": Unit.objects.count(),
            "owners": Owner.objects.count(),
            "tenants": Tenant.objects.count(),
            "managers": Manager.objects.count(),
            "active_leases": active_leases.count(),
            "vacant_units": Unit.objects.exclude(
                leases__status=LeaseAgreement.Status.AKTIV
            ).distinct().count(),
        }

        lease_balances = active_leases.annotate(
            soll_total=Coalesce(
                Sum(
                    "buchungen__brutto",
                    filter=Q(buchungen__typ=Buchung.Typ.SOLL),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Value(Decimal("0.00")),
            ),
            haben_total=Coalesce(
                Sum(
                    "buchungen__brutto",
                    filter=Q(buchungen__typ=Buchung.Typ.IST),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Value(Decimal("0.00")),
            ),
        )

        total_open_amount = Decimal("0.00")
        overdue_leases = 0
        for lease in lease_balances:
            saldo = (Decimal(lease.haben_total) - Decimal(lease.soll_total)).quantize(
                Decimal("0.01")
            )
            if saldo < Decimal("0.00"):
                overdue_leases += 1
                total_open_amount += -saldo

        context["stats"] = stats
        context["finance"] = {
            "overdue_leases": overdue_leases,
            "open_amount_total": total_open_amount.quantize(Decimal("0.01")),
        }
        context["recent_bookings"] = (
            Buchung.objects.select_related("mietervertrag__unit__property", "einheit")
            .order_by("-datum", "-id")[:6]
        )
        context["upcoming_exits"] = (
            active_leases.select_related("unit", "unit__property")
            .prefetch_related("tenants")
            .filter(exit_date__isnull=False, exit_date__gte=today)
            .order_by("exit_date")[:5]
        )
        property_cards = list(
            Property.objects.annotate(
            unit_count=Count("units", distinct=True),
            rented_unit_count=Count(
                "units",
                filter=Q(units__leases__status=LeaseAgreement.Status.AKTIV),
                distinct=True,
            ),
            ).order_by("name")[:6]
        )
        for property_card in property_cards:
            property_card.vacant_unit_count = max(
                property_card.unit_count - property_card.rented_unit_count,
                0,
            )
        context["property_cards"] = property_cards
        reminder_service = ReminderService(today=today)
        reminder_items = reminder_service.collect_items()
        context["reminder_summary"] = reminder_service.build_summary(reminder_items)
        context["upcoming_reminders"] = reminder_service.top_items(reminder_items, limit=8)
        return context


class DateiUploadView(View):
    http_method_names = ["post"]
    form_class = DateiUploadForm

    @staticmethod
    def _validation_messages(form):
        for field_name, errors in form.errors.as_data().items():
            field = form.fields.get(field_name)
            label = getattr(field, "label", "") if field else ""
            for error in errors:
                for message in error.messages:
                    if field_name == "__all__" or not label:
                        yield message
                    else:
                        yield f"{label}: {message}"

    def post(self, request, *args, **kwargs):
        next_url = request.POST.get("next") or reverse_lazy("dashboard")
        form = self.form_class(request.POST, request.FILES)
        if not form.is_valid():
            for message_text in self._validation_messages(form):
                messages.error(request, message_text)
            return redirect(next_url)

        try:
            datei = form.save()
        except ValidationError as exc:
            if isinstance(exc, ValidationError) and getattr(exc, "messages", None):
                messages.error(request, " ".join(exc.messages))
            else:
                messages.error(request, str(exc))
            return redirect(next_url)

        messages.success(request, "Datei wurde hochgeladen.")
        if datei.duplicate_of_id:
            messages.warning(
                request,
                "Hinweis: Die Datei ist inhaltlich bereits vorhanden und wurde als Duplikat markiert.",
            )
        return redirect(next_url)


class DateiDownloadView(View):
    http_method_names = ["get"]

    def get(self, request, pk, *args, **kwargs):
        datei = get_object_or_404(
            Datei.objects.prefetch_related("zuordnungen__content_type"),
            pk=pk,
        )
        download_target = datei
        replacement = DateiService.replacement_for_archived_download(datei=datei)
        if replacement is not None:
            download_target = replacement

        DateiService.prepare_download(user=None, datei=download_target)
        if not download_target.file:
            raise Http404("Datei wurde nicht gefunden.")

        download_name = download_target.original_name or os.path.basename(download_target.file.name or "")
        response = FileResponse(
            download_target.file.open("rb"),
            as_attachment=True,
            filename=download_name,
        )
        response["Content-Type"] = "application/octet-stream"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class DateiPreviewView(View):
    http_method_names = ["get"]

    def get(self, request, pk, *args, **kwargs):
        datei = get_object_or_404(
            Datei.objects.prefetch_related("zuordnungen__content_type"),
            pk=pk,
        )
        DateiService.prepare_download(user=None, datei=datei)
        if not datei.file:
            raise Http404("Datei wurde nicht gefunden.")

        mime_type = (datei.mime_type or "").lower()
        if not mime_type.startswith("image/"):
            raise Http404("Für diese Datei ist keine Vorschau verfügbar.")

        response = FileResponse(
            datei.file.open("rb"),
            as_attachment=False,
        )
        response["Content-Type"] = mime_type
        return response


class DateiArchiveView(View):
    http_method_names = ["post"]

    def post(self, request, pk, *args, **kwargs):
        next_url = request.POST.get("next") or reverse_lazy("dashboard")
        datei = get_object_or_404(Datei, pk=pk)
        DateiService.archive(user=None, datei=datei)

        messages.success(request, "Datei wurde archiviert.")
        return redirect(next_url)


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
        context["attachments_panel"] = build_attachments_panel_context(
            self.request,
            self.object,
            title="Dateien zur Liegenschaft",
        )
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


class ReminderSettingsView(TemplateView):
    template_name = "webapp/reminder_settings.html"

    def _build_formset(self, *, data=None):
        queryset = ReminderRuleConfig.objects.order_by("sort_order", "code")
        if data is not None:
            return ReminderRuleConfigFormSet(data=data, queryset=queryset)
        return ReminderRuleConfigFormSet(queryset=queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["formset"] = kwargs.get("formset") or self._build_formset()
        return context

    def post(self, request, *args, **kwargs):
        formset = self._build_formset(data=request.POST)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Erinnerungsregeln wurden gespeichert.")
            return redirect("reminder_settings")
        messages.error(request, "Bitte prüfen Sie die Eingaben bei den Erinnerungsregeln.")
        return self.render_to_response(self.get_context_data(formset=formset))


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attachments_panel"] = build_attachments_panel_context(
            self.request,
            self.object,
            title="Dateien zum Mieter",
        )
        return context


class TenantDeleteView(DeleteView):
    model = Tenant
    template_name = "webapp/tenant_confirm_delete.html"
    success_url = reverse_lazy("tenant_list")


class LeaseAgreementListView(ListView):
    model = LeaseAgreement
    template_name = "webapp/lease_list.html"
    context_object_name = "leases"
    queryset = LeaseAgreement.objects.select_related("unit", "manager").prefetch_related("tenants")
    unit_ordering = ("unit__name", "unit__property__name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        reminder_service = ReminderService(today=timezone.localdate())
        reminder_items = reminder_service.collect_items()
        reminders_by_lease = reminder_service.items_by_lease(reminder_items)

        active_leases = list(
            self.queryset.filter(status=LeaseAgreement.Status.AKTIV).order_by(*self.unit_ordering)
        )
        for lease in active_leases:
            lease.reminder_items = reminders_by_lease.get(lease.pk, [])

        ended_leases = list(
            self.queryset.filter(status=LeaseAgreement.Status.BEENDET).order_by(*self.unit_ordering)
        )
        for lease in ended_leases:
            lease.reminder_items = []

        context["active_leases"] = active_leases
        context["ended_leases"] = ended_leases
        context["lease_reminder_total"] = len(reminder_items)
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attachments_panel"] = build_attachments_panel_context(
            self.request,
            self.object,
            title="Dateien zum Mietverhältnis",
        )
        return context


class LeaseAgreementDeleteView(DeleteView):
    model = LeaseAgreement
    template_name = "webapp/lease_confirm_delete.html"
    success_url = reverse_lazy("lease_list")


class LeaseAgreementDetailView(DetailView):
    model = LeaseAgreement
    template_name = "webapp/lease_detail.html"
    context_object_name = "lease"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        buchungen = list(
            Buchung.objects.filter(mietervertrag=self.object)
            .select_related("bank_transaktion")
            .order_by("datum", "id")
        )
        cent = Decimal("0.01")
        soll_summe = Decimal("0.00")
        haben_summe = Decimal("0.00")
        kontostand = Decimal("0.00")
        konto_rows = []
        monat_key = None
        monat_soll = Decimal("0.00")
        monat_haben = Decimal("0.00")
        monat_start_kontostand = Decimal("0.00")

        def append_monatsabschluss(year, month):
            nonlocal monat_soll, monat_haben, monat_start_kontostand
            monat_delta = monat_haben - monat_soll
            monat_ende_kontostand = monat_start_kontostand + monat_delta
            offen = Decimal("0.00")
            if monat_ende_kontostand < 0:
                offen = (-monat_ende_kontostand).quantize(cent)
            konto_rows.append(
                {
                    "kind": "month_summary",
                    "month_key": (year, month),
                    "month_label": f"{month:02d}.{year}",
                    "month_soll": monat_soll.quantize(cent),
                    "month_haben": monat_haben.quantize(cent),
                    "month_delta": monat_delta.quantize(cent),
                    "month_end_kontostand": monat_ende_kontostand.quantize(cent),
                    "offen": offen,
                }
            )
            monat_soll = Decimal("0.00")
            monat_haben = Decimal("0.00")
            monat_start_kontostand = monat_ende_kontostand

        for buchung in buchungen:
            key = (buchung.datum.year, buchung.datum.month)
            if monat_key != key:
                if monat_key is not None:
                    append_monatsabschluss(monat_key[0], monat_key[1])
                monat_key = key
                monat_start_kontostand = kontostand

            if buchung.typ == Buchung.Typ.IST:
                kontobewegung = Decimal(buchung.brutto)
                haben_summe += Decimal(buchung.brutto)
                monat_haben += Decimal(buchung.brutto)
            else:
                kontobewegung = -Decimal(buchung.brutto)
                soll_summe += Decimal(buchung.brutto)
                monat_soll += Decimal(buchung.brutto)
            kontostand += kontobewegung
            buchung.kontobewegung = kontobewegung.quantize(cent)
            buchung.kontostand = kontostand.quantize(cent)
            konto_rows.append({"kind": "booking", "buchung": buchung})

        if monat_key is not None:
            append_monatsabschluss(monat_key[0], monat_key[1])

        konto_rows.reverse()
        if buchungen:
            latest_month_key = (buchungen[-1].datum.year, buchungen[-1].datum.month)
            konto_rows = [
                row
                for row in konto_rows
                if (
                    row["kind"] == "month_summary" and row.get("month_key") == latest_month_key
                )
                or (
                    row["kind"] == "booking"
                    and (
                        row["buchung"].datum.year,
                        row["buchung"].datum.month,
                    )
                    == latest_month_key
                )
            ]

        context["buchungen"] = buchungen
        context["konto_rows"] = konto_rows
        context["soll_summe"] = soll_summe.quantize(cent)
        context["haben_summe"] = haben_summe.quantize(cent)
        context["kontostand"] = kontostand.quantize(cent)
        context["attachments_panel"] = build_attachments_panel_context(
            self.request,
            self.object,
            title="Dateien zum Mietverhältnis",
        )
        return context


class MeterListView(ListView):
    model = Meter
    template_name = "webapp/meter_list.html"
    context_object_name = "meters"
    queryset = Meter.objects.select_related("property", "unit").order_by("unit__name", "meter_type", "meter_number")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        grouped = []
        current_key = None
        current_group = None

        for meter in context["meters"]:
            key = (meter.property_id, meter.unit_id)
            if key != current_key:
                if meter.unit:
                    label = f"{meter.property.name} · {meter.unit.name}"
                else:
                    label = f"{meter.property.name} (Allgemein)"
                current_group = {"label": label, "meters": []}
                grouped.append(current_group)
                current_key = key
            current_group["meters"].append(meter)

        context["grouped_meters"] = grouped
        return context


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


class MeterReadingByMeterListView(ListView):
    model = MeterReading
    template_name = "webapp/meter_reading_by_meter_list.html"
    context_object_name = "readings"

    def get_queryset(self):
        return (
            MeterReading.objects.select_related("meter", "meter__unit", "meter__property")
            .filter(meter_id=self.kwargs["pk"])
            .order_by("-date", "-id")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        meter = Meter.objects.select_related("unit", "property").get(pk=self.kwargs["pk"])
        context["meter"] = meter

        readings = list(context["readings"])
        last_reading_by_year: dict[int, MeterReading] = {}
        for index, reading in enumerate(readings):
            previous_reading = readings[index + 1] if index + 1 < len(readings) else None
            if previous_reading is None:
                reading.last_consumption = None
            else:
                reading.last_consumption = reading.value - previous_reading.value
            if reading.date.year not in last_reading_by_year:
                last_reading_by_year[reading.date.year] = reading
        context["readings"] = readings

        yearly_rows = Meter._calculate_yearly_consumption_for_meter(meter, readings)
        yearly_map = {row["calc_year"]: row["consumption"] for row in yearly_rows}
        for reading in readings:
            if last_reading_by_year.get(reading.date.year) is reading:
                reading.yearly_consumption = yearly_map.get(reading.date.year)
            else:
                reading.yearly_consumption = None
        context["attachments_panel"] = build_attachments_panel_context(
            self.request,
            meter,
            title="Dateien zum Verbrauchszähler",
        )
        return context


class MeterReadingCreateView(CreateView):
    model = MeterReading
    form_class = MeterReadingForm
    template_name = "webapp/meter_reading_form.html"
    success_url = reverse_lazy("meter_list")

    def _selected_meter(self):
        meter_id = self.request.GET.get("meter") or self.request.POST.get("meter")
        if not meter_id:
            return None
        try:
            meter_pk = int(meter_id)
        except (TypeError, ValueError):
            return None
        return (
            Meter.objects.select_related("unit", "property")
            .filter(pk=meter_pk)
            .first()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        meter = self._selected_meter()
        if meter:
            context["attachments_panel"] = build_attachments_panel_context(
                self.request,
                meter,
                title="Dateien zum Verbrauchszähler",
            )
        return context

    def get_initial(self):
        initial = super().get_initial()
        meter_id = self.request.GET.get("meter")
        if meter_id and Meter.objects.filter(pk=meter_id).exists():
            initial["meter"] = meter_id
        return initial

    def get_success_url(self):
        if self.request.GET.get("meter"):
            return reverse_lazy("meter_list")
        return reverse_lazy("meter_list")


class MeterReadingUpdateView(UpdateView):
    model = MeterReading
    form_class = MeterReadingForm
    template_name = "webapp/meter_reading_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attachments_panel"] = build_attachments_panel_context(
            self.request,
            self.object.meter,
            title="Dateien zum Verbrauchszähler",
        )
        return context

    def get_success_url(self):
        return reverse_lazy("meter_reading_by_meter_list", kwargs={"pk": self.object.meter_id})


class MeterReadingDeleteView(DeleteView):
    model = MeterReading
    template_name = "webapp/meter_reading_confirm_delete.html"

    def get_success_url(self):
        return reverse_lazy("meter_reading_by_meter_list", kwargs={"pk": self.object.meter_id})


class BankImportView(TemplateView):
    template_name = "webapp/bank_import.html"
    form_class = BankImportForm
    preview_session_key = "bank_import_preview_rows"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or self.form_class()
        context["preview_rows"] = self.request.session.get(self.preview_session_key, [])
        context["property_choices"] = [
            {"id": property_obj.pk, "label": property_obj.name}
            for property_obj in Property.objects.order_by("name")
        ]
        ungrouped_group, _created = BetriebskostenGruppe.get_or_create_ungrouped()
        group_queryset = BetriebskostenGruppe.objects.filter(
            Q(is_active=True) | Q(pk=ungrouped_group.pk)
        ).order_by("sort_order", "name", "id")
        context["bk_group_choices"] = [
            {"id": group.pk, "label": group.name}
            for group in group_queryset
        ]
        context["bk_art_choices"] = [
            {"id": choice_value, "label": choice_label}
            for choice_value, choice_label in BetriebskostenBeleg.BKArt.choices
        ]
        context["lease_choices"] = [
            {"id": lease.pk, "label": lease_display_name(lease)}
            for lease in (
                LeaseAgreement.objects.select_related("unit", "unit__property")
                .prefetch_related("tenants")
                .order_by("unit__property__name", "unit__name")
            )
        ]
        context["preview_count"] = len(context["preview_rows"])
        context["selected_count"] = sum(
            1 for row in context["preview_rows"] if self._is_preview_row_assigned(row)
        )
        context["auto_matched_count"] = sum(
            1 for row in context["preview_rows"] if row.get("auto_matched")
        )
        return context

    @staticmethod
    def _is_preview_row_assigned(row):
        if row.get("dismiss"):
            return False
        booking_type = row.get("booking_type")
        if booking_type == "bk":
            return bool(row.get("bk_property_id") and row.get("bk_group_id"))
        return bool(row.get("lease_id") or row.get("auto_split"))

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action") or "preview"
        if action == "confirm":
            return self._confirm_preview(request)
        if action == "discard":
            request.session.pop(self.preview_session_key, None)
            messages.info(request, "Die Import-Vorschau wurde verworfen.")
            return redirect("bank_import")

        form = self.form_class(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Bitte eine gültige JSON-Datei auswählen.")
            return self.render_to_response(self.get_context_data(form=form))

        upload = form.cleaned_data["json_file"]
        try:
            payload = json.load(upload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            messages.error(request, "Die Datei konnte nicht als JSON gelesen werden.")
            return self.render_to_response(self.get_context_data(form=form))

        items = self._normalize_payload(payload)
        if not items:
            messages.warning(request, "Keine Transaktionen in der Datei gefunden.")
            return self.render_to_response(self.get_context_data(form=form))

        preview_rows = self._build_preview_rows(items)
        if not preview_rows:
            messages.warning(request, "Keine buchbaren Transaktionen in der Datei gefunden.")
            return self.render_to_response(self.get_context_data(form=form))

        request.session[self.preview_session_key] = preview_rows
        request.session.modified = True
        messages.success(
            request,
            f"{len(preview_rows)} Transaktionen in Vorschau geladen. Bitte Zuweisungen prüfen und bestätigen.",
        )
        return redirect("bank_import")

    def _build_preview_rows(self, items):
        preview_rows = []
        skipped_count = 0
        duplicate_count = 0
        seen_references = set()
        ungrouped_group, _created = BetriebskostenGruppe.get_or_create_ungrouped()
        ungrouped_group_id = str(ungrouped_group.pk)

        leases = list(
            LeaseAgreement.objects.select_related("unit", "unit__property")
            .prefetch_related("tenants")
        )
        iban_map = build_lease_iban_map(leases)
        property_name_map = {
            (property_obj.name or "").strip().casefold(): str(property_obj.pk)
            for property_obj in Property.objects.only("id", "name")
        }

        for item in items:
            if not isinstance(item, dict):
                skipped_count += 1
                continue
            reference_number = (item.get("referenceNumber") or "").strip()
            if not reference_number:
                skipped_count += 1
                continue
            if reference_number in seen_references:
                duplicate_count += 1
                continue

            amount_data = item.get("amount") or {}
            try:
                amount_value = amount_data.get("value")
                amount_precision = amount_data.get("precision", 0)
                amount = self._parse_amount(amount_value, amount_precision)
                booking_date = self._parse_date(
                    item.get("booking")
                    or item.get("valuation")
                    or item.get("transactionDateTime")
                )
            except (InvalidOperation, ValueError, TypeError):
                skipped_count += 1
                continue
            if amount is None or booking_date is None:
                skipped_count += 1
                continue

            partner_account = item.get("partnerAccount") or {}
            iban = partner_account.get("iban") if isinstance(partner_account, dict) else ""
            purpose = (item.get("reference") or item.get("receiverReference") or "").strip()
            partner_name = (item.get("partnerName") or "").strip()

            candidates = matching_leases_for_transaction(
                iban=iban,
                purpose=purpose,
                booking_date=booking_date,
                active_leases=leases,
                iban_map=iban_map,
            )
            selected_lease, auto_reason, split_allocations = find_auto_lease_for_row(
                candidates=candidates,
                amount=amount,
                booking_date=booking_date,
            )
            selected_property_id = ""
            if selected_lease and selected_lease.unit and selected_lease.unit.property_id:
                selected_property_id = str(selected_lease.unit.property_id)
            elif len(candidates) == 1 and candidates[0].unit and candidates[0].unit.property_id:
                selected_property_id = str(candidates[0].unit.property_id)
            row_defaults = infer_bank_import_row_defaults(
                partner_name=partner_name,
                purpose=purpose,
                amount=amount,
                property_name_map=property_name_map,
            )
            row_defaults["bk_group_id"] = row_defaults.get("bk_group_id") or ungrouped_group_id

            preview_rows.append(
                {
                    "reference_number": reference_number,
                    "partner_name": partner_name,
                    "iban": iban or "",
                    "purpose": purpose,
                    "booking_date": booking_date.isoformat(),
                    "booking_date_display": booking_date.strftime("%d.%m.%Y"),
                    "amount": str(amount.quantize(Decimal("0.01"))),
                    "bookable": amount != Decimal("0.00"),
                    "bookable_for_miete": amount > Decimal("0.00"),
                    "bookable_for_bk": amount != Decimal("0.00"),
                    "booking_type": row_defaults["booking_type"],
                    "candidate_lease_ids": [lease.pk for lease in candidates],
                    "lease_id": str(selected_lease.pk) if selected_lease else "",
                    "bk_property_id": row_defaults["bk_property_id"] or selected_property_id,
                    "bk_group_id": row_defaults["bk_group_id"],
                    "bk_art": row_defaults["bk_art"],
                    "bk_ust_prozent": row_defaults["bk_ust_prozent"],
                    "dismiss": row_defaults["dismiss"],
                    "is_settlement_adjustment": row_defaults["is_settlement_adjustment"],
                    "suggested_settlement_adjustment": row_defaults[
                        "suggested_settlement_adjustment"
                    ],
                    "settlement_match_reason": row_defaults["settlement_match_reason"],
                    "auto_matched": bool(selected_lease or split_allocations),
                    "auto_split": bool(split_allocations),
                    "auto_split_allocations": [
                        {
                            "lease_id": str(allocation["lease"].pk),
                            "lease_label": lease_display_name(allocation["lease"]),
                            "amount": str(allocation["amount"].quantize(Decimal("0.01"))),
                        }
                        for allocation in split_allocations
                    ],
                    "auto_reason": auto_reason or "",
                }
            )
            seen_references.add(reference_number)

        if skipped_count:
            messages.warning(
                self.request,
                f"{skipped_count} Einträge wurden wegen fehlender Daten übersprungen.",
            )
        if duplicate_count:
            messages.warning(
                self.request,
                f"{duplicate_count} doppelte Referenznummern in der Datei wurden ignoriert.",
            )
        return preview_rows

    def _confirm_preview(self, request):
        preview_rows = request.session.get(self.preview_session_key, [])
        if not preview_rows:
            messages.warning(request, "Keine Vorschau vorhanden. Bitte zuerst eine Datei hochladen.")
            return redirect("bank_import")

        leases_by_id = {
            str(lease.pk): lease
            for lease in (
                LeaseAgreement.objects.select_related("unit")
            )
        }
        properties_by_id = {
            str(property_obj.pk): property_obj
            for property_obj in Property.objects.all()
        }
        ungrouped_group, _created = BetriebskostenGruppe.get_or_create_ungrouped()
        groups_by_id = {
            str(group.pk): group
            for group in BetriebskostenGruppe.objects.filter(
                Q(is_active=True) | Q(pk=ungrouped_group.pk)
            )
        }
        valid_bk_art_values = {choice for choice, _ in BetriebskostenBeleg.BKArt.choices}

        created_buchungen = []
        created_belege = []
        remaining_rows = []
        created_buchung_count = 0
        created_beleg_count = 0
        duplicate_count = 0
        unassigned_count = 0
        non_bookable_count = 0
        discarded_non_bookable_count = 0
        dismissed_count = 0

        for index, row in enumerate(preview_rows):
            dismiss_row = (request.POST.get(f"dismiss_{index}") or "").strip().lower() in {
                "1",
                "true",
                "on",
                "yes",
            }
            if dismiss_row:
                dismissed_count += 1
                continue

            selected_booking_type = (
                request.POST.get(f"type_{index}") or row.get("booking_type") or "miete"
            ).strip().lower()
            if selected_booking_type not in {"miete", "bk"}:
                selected_booking_type = "miete"
            row["booking_type"] = selected_booking_type
            selected_lease_id = (request.POST.get(f"lease_{index}") or "").strip()
            row["lease_id"] = selected_lease_id
            selected_property_id = (request.POST.get(f"bk_property_{index}") or "").strip()
            row["bk_property_id"] = selected_property_id
            selected_group_id = (
                request.POST.get(f"bk_group_{index}")
                or row.get("bk_group_id")
                or str(ungrouped_group.pk)
            ).strip()
            row["bk_group_id"] = selected_group_id
            selected_bk_art = (
                request.POST.get(f"bk_art_{index}") or row.get("bk_art") or BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN
            ).strip()
            if selected_bk_art not in valid_bk_art_values:
                selected_bk_art = BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN
            row["bk_art"] = selected_bk_art
            selected_ust_raw = (
                request.POST.get(f"bk_ust_{index}") or row.get("bk_ust_prozent") or "20.00"
            ).strip()
            row["bk_ust_prozent"] = selected_ust_raw
            selected_settlement_adjustment = (
                request.POST.get(f"settlement_adjustment_{index}", "0") or "0"
            ).strip().lower() in {
                "1",
                "true",
                "on",
                "yes",
            }
            row["is_settlement_adjustment"] = selected_settlement_adjustment

            reference_number = row["reference_number"]

            try:
                amount = Decimal(row["amount"]).quantize(Decimal("0.01"))
                booking_date = date.fromisoformat(row["booking_date"])
            except (InvalidOperation, ValueError, TypeError):
                unassigned_count += 1
                remaining_rows.append(row)
                continue
            if amount == Decimal("0.00"):
                non_bookable_count += 1
                discarded_non_bookable_count += 1
                continue

            if selected_booking_type == "miete":
                import_prefix = f"BANKIMPORT [{reference_number}]"
                already_exists = Buchung.objects.filter(
                    typ=Buchung.Typ.IST,
                    kategorie=Buchung.Kategorie.ZAHLUNG,
                    buchungstext__startswith=import_prefix,
                ).exists()
                if already_exists:
                    duplicate_count += 1
                    continue

                if amount <= Decimal("0.00"):
                    non_bookable_count += 1
                    remaining_rows.append(row)
                    continue

                if not selected_lease_id and row.get("auto_split_allocations"):
                    split_entries = []
                    split_invalid = False
                    for allocation in row.get("auto_split_allocations", []):
                        split_lease = leases_by_id.get(str(allocation.get("lease_id")))
                        try:
                            split_amount = Decimal(str(allocation.get("amount"))).quantize(
                                Decimal("0.01")
                            )
                        except (InvalidOperation, ValueError, TypeError):
                            split_invalid = True
                            break
                        if not split_lease or split_amount <= Decimal("0.00"):
                            split_invalid = True
                            break
                        split_entries.extend(
                            build_import_payment_entries_for_lease(
                                lease=split_lease,
                                gross_amount=split_amount,
                                booking_date=booking_date,
                                reference_number=reference_number,
                                purpose=row.get("purpose", ""),
                                is_settlement_adjustment=selected_settlement_adjustment,
                            )
                        )
                    if split_invalid or not split_entries:
                        unassigned_count += 1
                        remaining_rows.append(row)
                        continue
                    created_buchungen.extend(split_entries)
                    continue

                if not selected_lease_id:
                    unassigned_count += 1
                    remaining_rows.append(row)
                    continue

                lease = leases_by_id.get(selected_lease_id)
                if not lease:
                    unassigned_count += 1
                    remaining_rows.append(row)
                    continue

                created_buchungen.extend(
                    build_import_payment_entries_for_lease(
                        lease=lease,
                        gross_amount=amount,
                        booking_date=booking_date,
                        reference_number=reference_number,
                        purpose=row.get("purpose", ""),
                        is_settlement_adjustment=selected_settlement_adjustment,
                    )
                )
                continue

            already_exists = BetriebskostenBeleg.objects.filter(
                import_quelle="bankimport",
                import_referenz=reference_number,
            ).exists()
            if already_exists:
                duplicate_count += 1
                continue

            if not selected_property_id:
                unassigned_count += 1
                remaining_rows.append(row)
                continue

            liegenschaft = properties_by_id.get(selected_property_id)
            if not liegenschaft:
                unassigned_count += 1
                remaining_rows.append(row)
                continue
            ausgabengruppe = groups_by_id.get(selected_group_id)
            if not ausgabengruppe:
                unassigned_count += 1
                remaining_rows.append(row)
                continue

            try:
                ust_prozent = Decimal(selected_ust_raw.replace(",", ".")).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            except (InvalidOperation, ValueError, TypeError):
                unassigned_count += 1
                remaining_rows.append(row)
                continue

            if ust_prozent < Decimal("0.00"):
                unassigned_count += 1
                remaining_rows.append(row)
                continue

            brutto = abs(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if ust_prozent == Decimal("0.00"):
                netto = brutto
            else:
                divisor = (Decimal("1.00") + (ust_prozent / Decimal("100"))).quantize(
                    Decimal("0.0001"),
                    rounding=ROUND_HALF_UP,
                )
                netto = (brutto / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            computed_brutto = (
                netto + (netto * ust_prozent / Decimal("100"))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            created_belege.append(
                BetriebskostenBeleg(
                    liegenschaft=liegenschaft,
                    bk_art=selected_bk_art,
                    ausgabengruppe=ausgabengruppe,
                    datum=booking_date,
                    netto=netto,
                    ust_prozent=ust_prozent,
                    brutto=computed_brutto,
                    lieferant_name=row.get("partner_name", ""),
                    iban=row.get("iban", ""),
                    buchungstext=row.get("purpose", ""),
                    import_referenz=reference_number,
                    import_quelle="bankimport",
                )
            )

        for buchung in created_buchungen:
            buchung.full_clean()
        for beleg in created_belege:
            beleg.full_clean()

        if created_buchungen:
            with transaction.atomic():
                Buchung.objects.bulk_create(created_buchungen)
            created_buchung_count = len(created_buchungen)
        if created_belege:
            with transaction.atomic():
                BetriebskostenBeleg.objects.bulk_create(created_belege)
            created_beleg_count = len(created_belege)

        if remaining_rows:
            request.session[self.preview_session_key] = remaining_rows
        else:
            request.session.pop(self.preview_session_key, None)
        request.session.modified = True

        if created_buchung_count:
            messages.success(request, f"{created_buchung_count} Zahlungen wurden als HABEN gebucht.")
        if created_beleg_count:
            messages.success(request, f"{created_beleg_count} Betriebskostenbelege wurden importiert.")
        if duplicate_count:
            messages.info(request, f"{duplicate_count} Transaktionen waren bereits importiert.")
        if unassigned_count:
            messages.warning(
                request,
                f"{unassigned_count} Zeilen sind noch nicht vollständig zugewiesen und bleiben in der Vorschau.",
            )
        if non_bookable_count:
            if discarded_non_bookable_count:
                messages.info(
                    request,
                    f"{discarded_non_bookable_count} Nullbeträge wurden aus der Vorschau entfernt.",
                )
            remaining_non_bookable = non_bookable_count - discarded_non_bookable_count
            if remaining_non_bookable > 0:
                messages.info(
                    request,
                    f"{remaining_non_bookable} Beträge passen nicht zum gewählten Buchungstyp und bleiben in der Vorschau.",
                )
        if dismissed_count:
            messages.info(request, f"{dismissed_count} Zeilen wurden verworfen.")
        return redirect("bank_import")

    @staticmethod
    def _normalize_payload(payload):
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if isinstance(payload.get("transactions"), list):
                return payload["transactions"]
            return [payload]
        return []

    @staticmethod
    def _parse_amount(value, precision):
        if value is None:
            return None
        precision = int(precision or 0)
        divisor = Decimal(10) ** precision
        amount = Decimal(str(value)) / divisor
        return amount.quantize(Decimal("0.01"))

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z").date()
            except ValueError:
                try:
                    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z").date()
                except ValueError:
                    try:
                        return date.fromisoformat(value[:10])
                    except ValueError:
                        return None
        return None

def normalize_iban(value):
    if not value:
        return ""
    return "".join(char for char in value if char.isalnum()).upper()


def build_lease_iban_map(active_leases):
    mapping = {}
    for lease in active_leases:
        for tenant in lease.tenants.all():
            normalized = normalize_iban(tenant.iban)
            if not normalized:
                continue
            mapping.setdefault(normalized, {})
            mapping[normalized][lease.pk] = lease
    return {iban: list(leases.values()) for iban, leases in mapping.items()}


def matching_leases_for_transaction(iban, purpose, booking_date, active_leases, iban_map):
    lease_map = {}
    normalized_iban = normalize_iban(iban)
    for lease in iban_map.get(normalized_iban, []):
        if lease_is_active_on(lease, booking_date):
            lease_map[lease.pk] = lease

    purpose_lower = (purpose or "").lower()
    if purpose_lower:
        for lease in active_leases:
            if not lease_is_active_on(lease, booking_date):
                continue
            if lease.pk in lease_map:
                continue
            unit_name = (lease.unit.name or "").lower() if lease.unit else ""
            unit_door = (lease.unit.door_number or "").lower() if lease.unit else ""
            tenant_tokens = []
            for tenant in lease.tenants.all():
                if tenant.first_name:
                    tenant_tokens.append(tenant.first_name.lower())
                if tenant.last_name:
                    tenant_tokens.append(tenant.last_name.lower())
            candidates = [unit_name, unit_door, *tenant_tokens]
            if any(token and token in purpose_lower for token in candidates):
                lease_map[lease.pk] = lease

    return list(lease_map.values())


def find_auto_lease_for_row(candidates, amount, booking_date):
    if not candidates:
        return None, "", []

    amount_matches_candidates = []
    for lease in candidates:
        expected = allocation_amount_for_lease(lease, booking_date)
        if amount_matches(amount, expected):
            amount_matches_candidates.append(lease)

    if len(amount_matches_candidates) == 1:
        return amount_matches_candidates[0], "Betrag passt zur Soll-Stellung", []

    split_allocations = find_unique_split_allocations(candidates, amount, booking_date)
    if split_allocations:
        return (
            None,
            f"Automatisch auf {len(split_allocations)} Verträge verteilt",
            split_allocations,
        )

    if len(candidates) == 1:
        return candidates[0], "Eindeutiger Treffer", []
    return None, "", []


def find_unique_split_allocations(candidates, amount, booking_date):
    if len(candidates) < 2:
        return []

    weighted_candidates = []
    for lease in candidates:
        allocation = allocation_amount_for_lease(lease, booking_date)
        if allocation is None or allocation <= Decimal("0.00"):
            continue
        weighted_candidates.append((lease, allocation))

    if len(weighted_candidates) < 2:
        return []

    matched_combos = []
    for size in range(2, len(weighted_candidates) + 1):
        for combo in combinations(weighted_candidates, size):
            total = sum((part for _, part in combo), Decimal("0.00")).quantize(
                Decimal("0.01")
            )
            if amount_matches(amount, total):
                matched_combos.append(combo)
                if len(matched_combos) > 1:
                    return []

    if len(matched_combos) != 1:
        return []

    return [
        {"lease": lease, "amount": part}
        for lease, part in matched_combos[0]
    ]


def allocation_amount_for_lease(lease, booking_date):
    month_start, month_end = month_bounds(booking_date)
    aggregates = Buchung.objects.filter(
        mietervertrag=lease,
        datum__gte=month_start,
        datum__lte=month_end,
    ).aggregate(
        soll=Coalesce(
            Sum(
                "brutto",
                filter=Q(typ=Buchung.Typ.SOLL),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            Value(Decimal("0.00")),
        ),
        haben=Coalesce(
            Sum(
                "brutto",
                filter=Q(typ=Buchung.Typ.IST),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            Value(Decimal("0.00")),
        ),
    )

    soll = Decimal(aggregates.get("soll") or Decimal("0.00")).quantize(Decimal("0.01"))
    haben = Decimal(aggregates.get("haben") or Decimal("0.00")).quantize(Decimal("0.01"))
    offen = (soll - haben).quantize(Decimal("0.01"))
    if offen > Decimal("0.00"):
        return offen
    return expected_monthly_soll_for_lease(lease, booking_date)


def expected_monthly_soll_for_lease(lease, booking_date):
    month_start, month_end = month_bounds(booking_date)
    soll_total = (
        Buchung.objects.filter(
            mietervertrag=lease,
            typ=Buchung.Typ.SOLL,
            datum__gte=month_start,
            datum__lte=month_end,
        ).aggregate(
            total=Coalesce(
                Sum(
                    "brutto",
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Value(Decimal("0.00")),
            )
        )["total"]
        or Decimal("0.00")
    )
    soll_total = Decimal(soll_total).quantize(Decimal("0.01"))
    if soll_total > 0:
        return soll_total
    return gross_total_for_lease(lease)


def lease_is_active_on(lease, check_date):
    if lease.entry_date and lease.entry_date > check_date:
        return False
    if lease.exit_date and lease.exit_date < check_date:
        return False
    if lease.status == LeaseAgreement.Status.AKTIV:
        return True
    if lease.status == LeaseAgreement.Status.BEENDET and lease.exit_date:
        return True
    return False


def month_bounds(check_date):
    month_start = date(check_date.year, check_date.month, 1)
    last_day = monthrange(month_start.year, month_start.month)[1]
    month_end = date(month_start.year, month_start.month, last_day)
    return month_start, month_end


def shift_month(month_start, delta):
    month_index = (month_start.year * 12 + (month_start.month - 1)) + delta
    year = month_index // 12
    month = (month_index % 12) + 1
    return date(year, month, 1)


def lease_display_name(lease):
    unit_label = lease.unit.name if lease.unit else "Ohne Einheit"
    property_label = lease.unit.property.name if lease.unit and lease.unit.property else "Ohne Objekt"
    tenant_label = ", ".join(
        f"{tenant.first_name} {tenant.last_name}".strip()
        for tenant in lease.tenants.all()
    )
    if not tenant_label:
        tenant_label = "Ohne Mieter"
    return f"{property_label} · {unit_label} · {tenant_label}"


def import_booking_text(reference_number, purpose):
    base_text = f"BANKIMPORT [{reference_number}]"
    if not purpose:
        return base_text
    suffix = purpose.strip()
    max_suffix = 255 - len(base_text) - 3
    if max_suffix <= 0:
        return base_text
    if len(suffix) > max_suffix:
        suffix = suffix[:max_suffix].rstrip()
    return f"{base_text} · {suffix}"


def infer_bk_art_from_bank_text(partner_name, purpose):
    haystack = f"{partner_name or ''} {purpose or ''}".lower()
    if "evn" in haystack or "strom" in haystack:
        return BetriebskostenBeleg.BKArt.STROM
    if "wasser" in haystack:
        return BetriebskostenBeleg.BKArt.WASSER
    return BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN


def infer_bank_import_row_defaults(partner_name, purpose, amount, property_name_map):
    amount_abs = Decimal(amount).copy_abs().quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    haystack = f"{partner_name or ''} {purpose or ''}".casefold()
    haystack_compact = "".join(haystack.split())
    haystack_alnum = "".join(char for char in haystack if char.isalnum())
    is_settlement_adjustment, settlement_match_reason = match_settlement_adjustment_text(
        partner_name,
        purpose,
    )
    defaults = {
        "booking_type": "miete" if Decimal(amount) > Decimal("0.00") else "bk",
        "bk_art": infer_bk_art_from_bank_text(partner_name, purpose),
        "bk_group_id": "",
        "bk_ust_prozent": "20.00",
        "bk_property_id": "",
        "dismiss": False,
        "is_settlement_adjustment": is_settlement_adjustment,
        "suggested_settlement_adjustment": is_settlement_adjustment,
        "settlement_match_reason": settlement_match_reason,
    }
    bhg14_property_id = property_name_map.get("bhg14", "")
    mhs69_property_id = property_name_map.get("mhs69", "")

    if "beitr.ktonr.:065015757" in haystack_compact and amount_abs == Decimal("7.10"):
        defaults.update(
            {
                "booking_type": "bk",
                "bk_art": BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
                "bk_ust_prozent": "0.00",
                "bk_property_id": bhg14_property_id,
            }
        )
    if "gehalt" in haystack and amount_abs == Decimal("120.00"):
        defaults.update(
            {
                "booking_type": "bk",
                "bk_art": BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
                "bk_ust_prozent": "0.00",
                "bk_property_id": bhg14_property_id,
            }
        )
    if "gehalt" in haystack and amount_abs == Decimal("200.00"):
        defaults["dismiss"] = True

    if mhs69_property_id and (
        "meidl.hptstr.69" in haystack or "meidlhptstr69" in haystack_alnum
    ):
        defaults["bk_property_id"] = mhs69_property_id

    return defaults


def build_import_payment_entries_for_lease(
    lease,
    gross_amount,
    booking_date,
    reference_number,
    purpose,
    *,
    is_settlement_adjustment=False,
):
    allocations = split_payment_gross_by_tax_rate(lease, gross_amount)
    text = import_booking_text(reference_number, purpose)
    entries = []
    for allocation in allocations:
        tax_percent = allocation["ust_prozent"]
        allocation_gross = allocation["brutto"]
        entries.append(
            Buchung(
                mietervertrag=lease,
                einheit=lease.unit,
                typ=Buchung.Typ.IST,
                kategorie=Buchung.Kategorie.ZAHLUNG,
                buchungstext=text,
                datum=booking_date,
                netto=netto_from_brutto_and_tax(allocation_gross, tax_percent),
                ust_prozent=tax_percent,
                brutto=allocation_gross,
                is_settlement_adjustment=bool(is_settlement_adjustment),
            )
        )
    return entries


def split_payment_gross_by_tax_rate(lease, gross_amount):
    gross_amount = Decimal(gross_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if gross_amount <= Decimal("0.00"):
        return []

    bucket_10, bucket_20 = expected_monthly_gross_tax_buckets(lease)
    if bucket_10 <= Decimal("0.00") and bucket_20 <= Decimal("0.00"):
        hmz_tax = hmz_tax_percent_for_unit(lease.unit)
        return [{"ust_prozent": hmz_tax, "brutto": gross_amount}]
    if bucket_10 > Decimal("0.00") and bucket_20 <= Decimal("0.00"):
        return [{"ust_prozent": Decimal("10.00"), "brutto": gross_amount}]
    if bucket_20 > Decimal("0.00") and bucket_10 <= Decimal("0.00"):
        return [{"ust_prozent": Decimal("20.00"), "brutto": gross_amount}]

    total = (bucket_10 + bucket_20).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if total <= Decimal("0.00"):
        hmz_tax = hmz_tax_percent_for_unit(lease.unit)
        return [{"ust_prozent": hmz_tax, "brutto": gross_amount}]

    gross_10 = (gross_amount * bucket_10 / total).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    gross_20 = (gross_amount - gross_10).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if gross_10 <= Decimal("0.00"):
        return [{"ust_prozent": Decimal("20.00"), "brutto": gross_amount}]
    if gross_20 <= Decimal("0.00"):
        return [{"ust_prozent": Decimal("10.00"), "brutto": gross_amount}]
    return [
        {"ust_prozent": Decimal("10.00"), "brutto": gross_10},
        {"ust_prozent": Decimal("20.00"), "brutto": gross_20},
    ]


def expected_monthly_gross_tax_buckets(lease):
    hmz_tax_percent = hmz_tax_percent_for_unit(lease.unit)
    hmz_tax_rate = hmz_tax_percent / Decimal("100")

    hmz_gross = (
        Decimal(lease.net_rent or Decimal("0.00")) * (Decimal("1.00") + hmz_tax_rate)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    bk_gross = (
        Decimal(lease.operating_costs_net or Decimal("0.00")) * Decimal("1.10")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    hk_gross = (
        Decimal(lease.heating_costs_net or Decimal("0.00")) * Decimal("1.20")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    bucket_10 = bk_gross
    bucket_20 = hk_gross
    if hmz_tax_percent == Decimal("10.00"):
        bucket_10 = (bucket_10 + hmz_gross).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        bucket_20 = (bucket_20 + hmz_gross).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return bucket_10, bucket_20


def hmz_tax_percent_for_unit(unit):
    if unit and unit.unit_type == Unit.UnitType.PARKING:
        return Decimal("20.00")
    return Decimal("10.00")


def netto_from_brutto_and_tax(brutto, tax_percent):
    brutto = Decimal(brutto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    tax_percent = Decimal(tax_percent).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if tax_percent <= Decimal("0.00"):
        return brutto
    divisor = Decimal("1.00") + (tax_percent / Decimal("100"))
    return (brutto / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def gross_total_for_lease(lease):
    if lease is None:
        return None
    total = lease.total_gross_rent
    if total is None:
        return None
    return Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def amount_matches(amount, expected):
    if amount is None or expected is None:
        return False
    amount_q = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    expected_q = Decimal(expected).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return amount_q == expected_q


class OffenePostenListView(TemplateView):
    template_name = "webapp/offene_posten.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        month_start = self._month_start_from_request()
        month_end = month_bounds(month_start)[1]
        month_label = month_start.strftime("%m.%Y")
        previous_month = shift_month(month_start, -1)
        next_month = shift_month(month_start, 1)

        active_leases = (
            LeaseAgreement.objects.select_related("unit", "unit__property")
            .prefetch_related("tenants")
            .filter(status=LeaseAgreement.Status.AKTIV, entry_date__lte=month_end)
            .filter(Q(exit_date__isnull=True) | Q(exit_date__gte=month_start))
            .annotate(
                vortrag_soll=Coalesce(
                    Sum(
                        "buchungen__brutto",
                        filter=Q(
                            buchungen__typ=Buchung.Typ.SOLL,
                            buchungen__datum__lt=month_start,
                        ),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Value(Decimal("0.00")),
                ),
                vortrag_haben=Coalesce(
                    Sum(
                        "buchungen__brutto",
                        filter=Q(
                            buchungen__typ=Buchung.Typ.IST,
                            buchungen__datum__lt=month_start,
                        ),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Value(Decimal("0.00")),
                ),
                soll_sum=Coalesce(
                    Sum(
                        "buchungen__brutto",
                        filter=Q(
                            buchungen__typ=Buchung.Typ.SOLL,
                            buchungen__datum__gte=month_start,
                            buchungen__datum__lte=month_end,
                        ),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Value(Decimal("0.00")),
                ),
                haben_sum=Coalesce(
                    Sum(
                        "buchungen__brutto",
                        filter=Q(
                            buchungen__typ=Buchung.Typ.IST,
                            buchungen__datum__gte=month_start,
                            buchungen__datum__lte=month_end,
                        ),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Value(Decimal("0.00")),
                ),
            )
            .order_by("unit__property__name", "unit__name")
        )

        rows = []
        total_vortrag = Decimal("0.00")
        total_soll = Decimal("0.00")
        total_haben = Decimal("0.00")
        total_endsaldo = Decimal("0.00")
        total_offen = Decimal("0.00")
        total_guthaben = Decimal("0.00")

        for lease in active_leases:
            vortrag_soll = Decimal(lease.vortrag_soll or Decimal("0.00")).quantize(Decimal("0.01"))
            vortrag_haben = Decimal(lease.vortrag_haben or Decimal("0.00")).quantize(Decimal("0.01"))
            vortrag = (vortrag_haben - vortrag_soll).quantize(Decimal("0.01"))
            soll = Decimal(lease.soll_sum or Decimal("0.00")).quantize(Decimal("0.01"))
            haben = Decimal(lease.haben_sum or Decimal("0.00")).quantize(Decimal("0.01"))
            endsaldo = (vortrag + haben - soll).quantize(Decimal("0.01"))
            offen = max(-endsaldo, Decimal("0.00")).quantize(Decimal("0.01"))
            guthaben = max(endsaldo, Decimal("0.00")).quantize(Decimal("0.01"))
            status_label, status_class = offene_posten_status(
                vortrag=vortrag,
                soll=soll,
                haben=haben,
                endsaldo=endsaldo,
            )

            rows.append(
                {
                    "lease": lease,
                    "vortrag": vortrag,
                    "soll": soll,
                    "haben": haben,
                    "endsaldo": endsaldo,
                    "offen": offen,
                    "guthaben": guthaben,
                    "status_label": status_label,
                    "status_class": status_class,
                }
            )
            total_vortrag += vortrag
            total_soll += soll
            total_haben += haben
            total_endsaldo += endsaldo
            total_offen += offen
            total_guthaben += guthaben

        context["month_label"] = month_label
        context["month_input_value"] = month_start.strftime("%Y-%m")
        context["previous_month_input"] = previous_month.strftime("%Y-%m")
        context["previous_month_label"] = previous_month.strftime("%m.%Y")
        context["next_month_input"] = next_month.strftime("%Y-%m")
        context["next_month_label"] = next_month.strftime("%m.%Y")
        context["rows"] = rows
        context["total_vortrag"] = total_vortrag.quantize(Decimal("0.01"))
        context["total_soll"] = total_soll.quantize(Decimal("0.01"))
        context["total_haben"] = total_haben.quantize(Decimal("0.01"))
        context["total_endsaldo"] = total_endsaldo.quantize(Decimal("0.01"))
        context["total_offen"] = total_offen.quantize(Decimal("0.01"))
        context["total_guthaben"] = total_guthaben.quantize(Decimal("0.01"))
        return context


    def _month_start_from_request(self):
        raw = (self.request.GET.get("monat") or "").strip()
        if raw:
            try:
                year_str, month_str = raw.split("-")
                return date(int(year_str), int(month_str), 1)
            except (ValueError, TypeError):
                pass
        today = timezone.localdate()
        return date(today.year, today.month, 1)


def offene_posten_status(vortrag, soll, haben, endsaldo):
    if vortrag == Decimal("0.00") and soll == Decimal("0.00") and haben == Decimal("0.00"):
        return "Keine Soll-Stellung", "secondary"
    if endsaldo == Decimal("0.00"):
        return "Ausgeglichen", "success"
    if endsaldo < Decimal("0.00") and vortrag == Decimal("0.00") and haben == Decimal("0.00") and soll > Decimal("0.00"):
        return "Nicht gezahlt", "danger"
    if endsaldo < Decimal("0.00") and vortrag == Decimal("0.00") and Decimal("0.00") < haben < soll:
        return "Teilzahlung", "warning"
    if endsaldo < Decimal("0.00"):
        return "Rückstand", "danger"
    return "Guthaben", "info"


class BuchungListView(ListView):
    model = Buchung
    template_name = "webapp/buchung_list.html"
    context_object_name = "buchungen"
    queryset = Buchung.objects.select_related(
        "mietervertrag",
        "einheit",
        "bank_transaktion",
    ).order_by("-datum", "-id")

    def get_queryset(self):
        queryset = super().get_queryset().filter(typ=Buchung.Typ.IST)
        self.bank_transaktion_id = (self.request.GET.get("bank_transaktion") or "").strip()
        if self.bank_transaktion_id:
            queryset = queryset.filter(bank_transaktion_id=self.bank_transaktion_id)

        self.properties = list(Property.objects.order_by("name"))
        self.selected_property = self._selected_property(self.properties)
        self.selected_property_id = str(self.selected_property.pk) if self.selected_property else ""
        if self.selected_property is not None:
            queryset = queryset.filter(
                Q(mietervertrag__unit__property=self.selected_property)
                | Q(einheit__property=self.selected_property)
            )

        self.year_choices = self._year_choices_for_queryset(queryset)
        self.selected_year = self._selected_year(self.year_choices)
        return queryset.filter(datum__year=self.selected_year)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["year_choices"] = getattr(self, "year_choices", [])
        context["selected_year"] = getattr(self, "selected_year", timezone.localdate().year)
        context["bank_transaktion_id"] = getattr(self, "bank_transaktion_id", "")
        context["properties"] = getattr(self, "properties", [])
        context["selected_property_id"] = getattr(self, "selected_property_id", "")
        context["selected_property_filter_value"] = getattr(self, "selected_property_filter_value", "")
        return context

    def _selected_property(self, properties):
        raw_property_filter = self.request.GET.get("liegenschaft")
        if raw_property_filter is not None:
            requested_property_id = raw_property_filter.strip()
            if requested_property_id in {"", "all"}:
                self.selected_property_filter_value = "all"
                return None
            for property_obj in properties:
                if str(property_obj.pk) == requested_property_id:
                    self.selected_property_filter_value = str(property_obj.pk)
                    return property_obj
            self.selected_property_filter_value = "all"
            return None

        if self.bank_transaktion_id:
            self.selected_property_filter_value = ""
            return None

        preferred_bhg14 = next(
            (
                property_obj
                for property_obj in properties
                if (property_obj.name or "").strip().casefold() == "bhg14"
            ),
            None,
        )
        if preferred_bhg14 is not None:
            self.selected_property_filter_value = str(preferred_bhg14.pk)
        else:
            self.selected_property_filter_value = ""
        return preferred_bhg14

    def _year_choices_for_queryset(self, queryset):
        years = sorted(
            {
                int(year_value)
                for year_value in queryset.values_list("datum__year", flat=True)
                if year_value is not None
            }
        )
        return years

    def _selected_year(self, year_choices):
        current_year = timezone.localdate().year
        raw_year = (self.request.GET.get("jahr") or "").strip()
        requested_year = None
        if raw_year.isdigit():
            requested_year = int(raw_year)
            if not (2000 <= requested_year <= 2100):
                requested_year = None

        if requested_year is not None and requested_year in year_choices:
            return requested_year
        if current_year in year_choices:
            return current_year
        if year_choices:
            return year_choices[-1]
        return current_year


class BuchungCreateView(CreateView):
    model = Buchung
    form_class = BuchungForm
    template_name = "webapp/buchung_form.html"
    success_url = reverse_lazy("buchung_list")

    def get_initial(self):
        initial = super().get_initial()
        lease_id = self.request.GET.get("lease")
        if lease_id and lease_id.isdigit():
            lease = (
                LeaseAgreement.objects.select_related("unit", "unit__property")
                .filter(pk=lease_id)
                .first()
            )
            if lease and lease.unit and lease.unit.property_id:
                initial["liegenschaft"] = lease.unit.property_id
                initial["einheit"] = lease.unit_id
                initial["typ"] = Buchung.Typ.SOLL
                initial["kategorie"] = Buchung.Kategorie.HMZ
                initial["buchungstext"] = "Manuelle Soll-Buchung (z. B. VPI-Anpassung)"
                initial["mietervertrag_prefill_id"] = lease.pk
                return initial
        property_id = self.request.GET.get("liegenschaft")
        if property_id:
            initial["liegenschaft"] = property_id
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if "initial" in kwargs and kwargs["initial"].get("mietervertrag_prefill_id"):
            kwargs["mietervertrag_prefill_id"] = kwargs["initial"]["mietervertrag_prefill_id"]
        return kwargs


class BuchungUpdateView(UpdateView):
    model = Buchung
    form_class = BuchungForm
    template_name = "webapp/buchung_form.html"
    success_url = reverse_lazy("buchung_list")


class BuchungDeleteView(DeleteView):
    model = Buchung
    template_name = "webapp/buchung_confirm_delete.html"
    success_url = reverse_lazy("buchung_list")


class BetriebskostenGruppeListView(ListView):
    model = BetriebskostenGruppe
    template_name = "webapp/betriebskosten_gruppe_list.html"
    context_object_name = "gruppen"
    queryset = BetriebskostenGruppe.objects.order_by("sort_order", "name", "id")


class BetriebskostenGruppeCreateView(CreateView):
    model = BetriebskostenGruppe
    form_class = BetriebskostenGruppeForm
    template_name = "webapp/betriebskosten_gruppe_form.html"
    success_url = reverse_lazy("betriebskosten_gruppe_list")


class BetriebskostenGruppeUpdateView(UpdateView):
    model = BetriebskostenGruppe
    form_class = BetriebskostenGruppeForm
    template_name = "webapp/betriebskosten_gruppe_form.html"
    success_url = reverse_lazy("betriebskosten_gruppe_list")


class BetriebskostenBelegListView(ListView):
    model = BetriebskostenBeleg
    template_name = "webapp/betriebskostenbeleg_list.html"
    context_object_name = "belege"
    queryset = BetriebskostenBeleg.objects.select_related("liegenschaft", "ausgabengruppe").order_by("-datum", "-id")

    def get_queryset(self):
        queryset = super().get_queryset()
        self.year_choices = self._year_choices_for_queryset(queryset)
        self.selected_year = self._selected_year(self.year_choices)
        return queryset.filter(datum__year=self.selected_year)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ungrouped_group, _created = BetriebskostenGruppe.get_or_create_ungrouped()
        context["bulk_group_choices"] = (
            BetriebskostenGruppe.objects.filter(Q(is_active=True) | Q(pk=ungrouped_group.pk))
            .order_by("sort_order", "name", "id")
        )
        context["year_choices"] = getattr(self, "year_choices", [])
        context["selected_year"] = getattr(self, "selected_year", timezone.localdate().year)
        return context

    def _year_choices_for_queryset(self, queryset):
        years = sorted(
            {
                int(year_value)
                for year_value in queryset.values_list("datum__year", flat=True)
                if year_value is not None
            }
        )
        return years

    def _selected_year(self, year_choices):
        current_year = timezone.localdate().year
        raw_year = (self.request.GET.get("jahr") or "").strip()
        requested_year = None
        if raw_year.isdigit():
            requested_year = int(raw_year)
            if not (2000 <= requested_year <= 2100):
                requested_year = None

        if requested_year is not None and requested_year in year_choices:
            return requested_year
        if current_year in year_choices:
            return current_year
        if year_choices:
            return year_choices[-1]
        return current_year


class BetriebskostenBelegCreateView(CreateView):
    model = BetriebskostenBeleg
    form_class = BetriebskostenBelegForm
    template_name = "webapp/betriebskostenbeleg_form.html"
    success_url = reverse_lazy("betriebskostenbeleg_list")

    def get_initial(self):
        initial = super().get_initial()
        initial["bk_art"] = BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN
        ungrouped_group, _created = BetriebskostenGruppe.get_or_create_ungrouped()
        initial["ausgabengruppe"] = ungrouped_group.pk

        requested_property_id = (self.request.GET.get("liegenschaft") or "").strip()
        if requested_property_id and Property.objects.filter(pk=requested_property_id).exists():
            initial["liegenschaft"] = requested_property_id
            return initial

        bhg14_property = (
            Property.objects.filter(name__iexact="BHG14")
            .order_by("id")
            .first()
        )
        if bhg14_property is not None:
            initial["liegenschaft"] = bhg14_property.pk
        return initial


class BetriebskostenBelegUpdateView(UpdateView):
    model = BetriebskostenBeleg
    form_class = BetriebskostenBelegForm
    template_name = "webapp/betriebskostenbeleg_form.html"

    def _get_valid_next_url(self):
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if not next_url:
            return None
        if url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return next_url
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next_url"] = self._get_valid_next_url() or reverse_lazy("betriebskostenbeleg_list")
        return context

    def get_success_url(self):
        return self._get_valid_next_url() or reverse_lazy("betriebskostenbeleg_list")


class BetriebskostenBelegDeleteView(DeleteView):
    model = BetriebskostenBeleg
    template_name = "webapp/betriebskostenbeleg_confirm_delete.html"
    success_url = reverse_lazy("betriebskostenbeleg_list")


class BetriebskostenBelegBulkGroupUpdateView(View):
    http_method_names = ["post"]

    def _get_valid_next_url(self):
        next_url = self.request.POST.get("next")
        if not next_url:
            return None
        if url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return next_url
        return None

    def post(self, request, *args, **kwargs):
        selected_ids_raw = request.POST.getlist("selected_belege")
        selected_group_id = (request.POST.get("bulk_group_id") or "").strip()
        next_url = self._get_valid_next_url() or reverse_lazy("betriebskostenbeleg_list")

        selected_ids: set[int] = set()
        for value in selected_ids_raw:
            if str(value).isdigit():
                selected_ids.add(int(value))
        if not selected_ids:
            messages.warning(request, "Bitte mindestens einen Beleg auswählen.")
            return redirect(next_url)

        ungrouped_group, _created = BetriebskostenGruppe.get_or_create_ungrouped()
        valid_groups_qs = BetriebskostenGruppe.objects.filter(
            Q(is_active=True) | Q(pk=ungrouped_group.pk)
        )
        selected_group = valid_groups_qs.filter(pk=selected_group_id).first()
        if selected_group is None:
            messages.warning(request, "Bitte eine gültige Ausgabengruppe auswählen.")
            return redirect(next_url)

        queryset = BetriebskostenBeleg.objects.filter(pk__in=selected_ids)
        if not queryset.exists():
            messages.warning(request, "Die ausgewählten Belege konnten nicht gefunden werden.")
            return redirect(next_url)

        with transaction.atomic():
            updated_count = queryset.update(ausgabengruppe=selected_group)
        messages.success(
            request,
            f"{updated_count} Beleg(e) wurden der Gruppe „{selected_group.name}“ zugewiesen.",
        )
        return redirect(next_url)


class BetriebskostenAbrechnungView(TemplateView):
    template_name = "webapp/betriebskosten_abrechnung.html"
    tabs = [
        ("uebersicht", "Übersicht"),
        ("bk-allgemein", "BK allg."),
        ("wasser", "Wasser"),
        ("warmwasser", "Warmwasser"),
        ("heizung", "Heizung"),
        ("allgemeinstrom", "Allgemeinstrom"),
        ("zusammenfassung", "Zusammenfassung"),
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        properties = list(Property.objects.order_by("name"))
        selected_property = self._selected_property(properties)
        selected_property_id = str(selected_property.pk) if selected_property else ""
        year_choices = self._available_years_for_property(selected_property)
        selected_year = self._selected_year(year_choices)
        selected_tab = (self.request.GET.get("reiter") or "uebersicht").strip().lower()
        valid_tabs = {tab_id for tab_id, _ in self.tabs}
        if selected_tab not in valid_tabs:
            selected_tab = "uebersicht"

        operating_cost_service = OperatingCostService(
            property=selected_property,
            year=selected_year,
        )
        report = operating_cost_service.get_report_data()

        financials = report["financials"]
        expenses = financials["expenses"]
        income = financials["income"]
        distribution = report["distribution"]["bk_allgemein"]
        allocations = report.get("allocations", {})

        ausgaben_strom = self._to_money_decimal(expenses.get("strom"))
        ausgaben_wasser = self._to_money_decimal(expenses.get("wasser"))
        ausgaben_betriebskosten = self._to_money_decimal(expenses.get("betriebskosten"))
        ausgaben_gesamt = self._to_money_decimal(expenses.get("gesamt"))
        einnahmen_betriebskosten = self._to_money_decimal(income.get("betriebskosten"))
        einnahmen_heizung = self._to_money_decimal(income.get("heizung"))
        einnahmen_gesamt = self._to_money_decimal(income.get("gesamt"))
        saldo = self._to_money_decimal(financials.get("saldo"))
        meter_consumption_groups = report["meter"].get("groups", [])
        bk_allg = self._deserialize_bk_allg(distribution)

        context["tabs"] = [{"id": tab_id, "label": label} for tab_id, label in self.tabs]
        context["selected_tab"] = selected_tab
        context["selected_tab_label"] = next(
            (label for tab_id, label in self.tabs if tab_id == selected_tab),
            "Übersicht",
        )
        context["selected_year"] = selected_year
        context["year_choices"] = year_choices
        context["properties"] = properties
        context["selected_property_id"] = selected_property_id
        context["selected_property"] = selected_property
        context["period_label"] = str(selected_year)
        context["operating_cost_report"] = report
        context["bk_distribution_legacy"] = allocations.get("bk_distribution", {})
        context["water_allocation"] = allocations.get("water", {})
        context["electricity_common_allocation"] = allocations.get("electricity_common", {})
        context["wp_metrics"] = allocations.get("wp_metrics", {})
        context["hot_water_allocation"] = allocations.get("hot_water", {})
        context["heating_allocation"] = allocations.get("heating", {})
        context["annual_statement"] = allocations.get("annual_statement", {})
        context["allocation_checks"] = allocations.get("checks", {})
        context["annual_statement_trace"] = self._build_annual_statement_trace(
            allocations=allocations
        )

        context["ausgaben_strom"] = ausgaben_strom
        context["ausgaben_wasser"] = ausgaben_wasser
        context["ausgaben_betriebskosten"] = ausgaben_betriebskosten
        context["ausgaben_gesamt"] = ausgaben_gesamt
        context["einnahmen_betriebskosten"] = einnahmen_betriebskosten
        context["einnahmen_heizung"] = einnahmen_heizung
        context["einnahmen_gesamt"] = einnahmen_gesamt
        context["saldo"] = saldo
        context["meter_consumption_groups"] = meter_consumption_groups
        context["bk_allg"] = bk_allg
        context["overview_finance_details"] = self._build_overview_finance_details(
            selected_property=selected_property,
            operating_cost_service=operating_cost_service,
        )
        return context

    def _build_overview_finance_details(self, *, selected_property, operating_cost_service):
        categories = [
            {"key": "betriebskosten", "label": "Betriebskosten"},
            {"key": "strom", "label": "Strom"},
            {"key": "wasser", "label": "Wasser"},
            {"key": "heizung", "label": "Heizung"},
        ]
        details_by_key = {
            item["key"]: {
                "key": item["key"],
                "label": item["label"],
                "expenses_rows": [],
                "expenses_sum": Decimal("0.00"),
                "income_rows": [],
                "income_sum": Decimal("0.00"),
            }
            for item in categories
        }

        if selected_property is None:
            return [details_by_key[item["key"]] for item in categories]

        expense_key_by_bk_art = {
            BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN: "betriebskosten",
            BetriebskostenBeleg.BKArt.SONSTIG: "betriebskosten",
            BetriebskostenBeleg.BKArt.STROM: "strom",
            BetriebskostenBeleg.BKArt.WASSER: "wasser",
        }
        expense_belege = (
            BetriebskostenBeleg.objects.filter(
                liegenschaft=selected_property,
                datum__gte=operating_cost_service.period_start,
                datum__lte=operating_cost_service.period_end,
            )
            .order_by("datum", "id")
        )
        for beleg in expense_belege:
            category_key = expense_key_by_bk_art.get(beleg.bk_art)
            if category_key is None:
                continue
            description = (beleg.buchungstext or "").strip() or (beleg.lieferant_name or "").strip() or "Ohne Buchungstext"
            details_by_key[category_key]["expenses_rows"].append(
                {
                    "date": beleg.datum,
                    "description": description,
                    "source": f"BK-Beleg · {beleg.get_bk_art_display()}",
                    "amount": self._to_money_decimal(beleg.netto),
                }
            )

        income_bookings = (
            Buchung.objects.filter(
                typ=Buchung.Typ.IST,
                is_settlement_adjustment=False,
                datum__gte=operating_cost_service.period_start,
                datum__lte=operating_cost_service.period_end,
            )
            .filter(
                Q(mietervertrag__unit__property=selected_property)
                | Q(einheit__property=selected_property)
            )
            .select_related("mietervertrag", "mietervertrag__unit", "einheit")
            .order_by("datum", "id")
        )
        for booking in income_bookings:
            netto = self._to_money_decimal(booking.netto)
            if netto <= Decimal("0.00"):
                continue

            reference = self._booking_reference_label(booking)
            description = (booking.buchungstext or "").strip() or "Ohne Buchungstext"

            if booking.kategorie == Buchung.Kategorie.BK:
                details_by_key["betriebskosten"]["income_rows"].append(
                    {
                        "date": booking.datum,
                        "description": description,
                        "source": "IST-Buchung · Betriebskosten",
                        "reference": reference,
                        "amount": netto,
                    }
                )
                continue
            if booking.kategorie == Buchung.Kategorie.HK:
                details_by_key["heizung"]["income_rows"].append(
                    {
                        "date": booking.datum,
                        "description": description,
                        "source": "IST-Buchung · Heizkosten",
                        "reference": reference,
                        "amount": netto,
                    }
                )
                continue
            if booking.kategorie != Buchung.Kategorie.ZAHLUNG:
                continue

            lease = booking.mietervertrag
            if lease is None:
                continue

            profile = operating_cost_service._soll_profile_for_month(
                lease=lease,
                booking_date=booking.datum,
            )
            bucket_key = operating_cost_service._rate_bucket_key(booking.ust_prozent)
            bucket_data = profile.get(bucket_key)
            if not bucket_data:
                continue

            bucket_total = self._to_money_decimal(bucket_data.get("total"))
            if bucket_total <= Decimal("0.00"):
                continue

            bucket_bk = self._to_money_decimal(bucket_data.get("bk"))
            bucket_hk = self._to_money_decimal(bucket_data.get("hk"))
            income_bk_share = (netto * bucket_bk / bucket_total).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            income_hk_share = (netto * bucket_hk / bucket_total).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            if income_bk_share > Decimal("0.00"):
                details_by_key["betriebskosten"]["income_rows"].append(
                    {
                        "date": booking.datum,
                        "description": description,
                        "source": "Anteil aus Zahlung",
                        "reference": reference,
                        "amount": income_bk_share,
                    }
                )
            if income_hk_share > Decimal("0.00"):
                details_by_key["heizung"]["income_rows"].append(
                    {
                        "date": booking.datum,
                        "description": description,
                        "source": "Anteil aus Zahlung",
                        "reference": reference,
                        "amount": income_hk_share,
                    }
                )

        for key in details_by_key:
            details_by_key[key]["expenses_sum"] = self._sum_detail_rows(
                details_by_key[key]["expenses_rows"]
            )
            details_by_key[key]["income_sum"] = self._sum_detail_rows(
                details_by_key[key]["income_rows"]
            )

        return [details_by_key[item["key"]] for item in categories]

    def _build_annual_statement_trace(self, *, allocations):
        annual_statement = allocations.get("annual_statement", {})
        annual_rows = annual_statement.get("rows", [])
        annual_totals = annual_statement.get("totals", {})

        bk_lookup = {
            row.get("unit_id"): self._to_money_decimal(row.get("anteil_euro"))
            for row in allocations.get("bk_distribution", {}).get("rows", [])
        }
        water_lookup = {
            row.get("unit_id"): self._to_money_decimal(row.get("cost_share"))
            for row in allocations.get("water", {}).get("rows", [])
        }
        electricity_lookup = {
            row.get("unit_id"): self._to_money_decimal(row.get("cost_share"))
            for row in allocations.get("electricity_common", {}).get("rows", [])
        }
        hot_water_lookup = {
            row.get("unit_id"): self._to_money_decimal(row.get("cost_share"))
            for row in allocations.get("hot_water", {}).get("rows", [])
        }
        heating_lookup = {
            row.get("unit_id"): {
                "fixed": self._to_money_decimal(row.get("fixed_cost_share")),
                "variable": self._to_money_decimal(row.get("variable_cost_share")),
                "total": self._to_money_decimal(row.get("cost_share")),
            }
            for row in allocations.get("heating", {}).get("rows", [])
        }

        trace_rows = []
        totals_brutto = {
            "gross_10": Decimal("0.00"),
            "gross_20": Decimal("0.00"),
            "ust_10": Decimal("0.00"),
            "ust_20": Decimal("0.00"),
            "akonto_bk_brutto": Decimal("0.00"),
            "akonto_hk_brutto": Decimal("0.00"),
        }
        for row in annual_rows:
            unit_id = row.get("unit_id")
            netto_10 = self._to_money_decimal(row.get("costs_net_10"))
            netto_20 = self._to_money_decimal(row.get("costs_net_20"))
            gross_10 = self._to_money_decimal(row.get("gross_10"))
            gross_20 = self._to_money_decimal(row.get("gross_20"))
            ust_10 = (gross_10 - netto_10).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            ust_20 = (gross_20 - netto_20).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            ust_total = (ust_10 + ust_20).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            netto_total = (netto_10 + netto_20).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            akonto_bk = self._to_money_decimal(row.get("akonto_bk"))
            akonto_hk = self._to_money_decimal(row.get("akonto_hk"))
            akonto_total = self._to_money_decimal(row.get("akonto_total"))
            akonto_bk_brutto = (akonto_bk * Decimal("1.10")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            akonto_hk_brutto = (akonto_hk * Decimal("1.20")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            akonto_total_brutto = (akonto_bk_brutto + akonto_hk_brutto).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            gross_total = self._to_money_decimal(row.get("gross_total"))
            saldo_brutto_10 = (akonto_bk_brutto - gross_10).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            saldo_brutto_20 = (akonto_hk_brutto - gross_20).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            saldo_brutto_total = (akonto_total_brutto - gross_total).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            saldo_netto = (akonto_total - netto_total).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            totals_brutto["gross_10"] = (totals_brutto["gross_10"] + gross_10).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            totals_brutto["gross_20"] = (totals_brutto["gross_20"] + gross_20).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            totals_brutto["ust_10"] = (totals_brutto["ust_10"] + ust_10).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            totals_brutto["ust_20"] = (totals_brutto["ust_20"] + ust_20).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            totals_brutto["akonto_bk_brutto"] = (
                totals_brutto["akonto_bk_brutto"] + akonto_bk_brutto
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            totals_brutto["akonto_hk_brutto"] = (
                totals_brutto["akonto_hk_brutto"] + akonto_hk_brutto
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            trace_rows.append(
                {
                    "unit_id": unit_id,
                    "label": row.get("label", ""),
                    "bk_allg": bk_lookup.get(unit_id, Decimal("0.00")),
                    "wasser": water_lookup.get(unit_id, Decimal("0.00")),
                    "allgemeinstrom": electricity_lookup.get(unit_id, Decimal("0.00")),
                    "warmwasser": hot_water_lookup.get(unit_id, Decimal("0.00")),
                    "heizung_fix": heating_lookup.get(unit_id, {}).get("fixed", Decimal("0.00")),
                    "heizung_variabel": heating_lookup.get(unit_id, {}).get(
                        "variable", Decimal("0.00")
                    ),
                    "heizung_total": heating_lookup.get(unit_id, {}).get("total", Decimal("0.00")),
                    "netto_10": netto_10,
                    "netto_20": netto_20,
                    "netto_total": netto_total,
                    "ust_10": ust_10,
                    "ust_20": ust_20,
                    "ust_total": ust_total,
                    "gross_10": gross_10,
                    "gross_20": gross_20,
                    "akonto_bk": akonto_bk,
                    "akonto_hk": akonto_hk,
                    "akonto_total": akonto_total,
                    "akonto_bk_brutto": akonto_bk_brutto,
                    "akonto_hk_brutto": akonto_hk_brutto,
                    "akonto_total_brutto": akonto_total_brutto,
                    "saldo_netto": saldo_netto,
                    "gross_total": gross_total,
                    "saldo_brutto_10": saldo_brutto_10,
                    "saldo_brutto_20": saldo_brutto_20,
                    "saldo_brutto": saldo_brutto_total,
                }
            )

        totals = {
            "netto_10": self._to_money_decimal(annual_totals.get("net_10")),
            "netto_20": self._to_money_decimal(annual_totals.get("net_20")),
            "gross_total": self._to_money_decimal(annual_totals.get("gross_total")),
            "akonto_total": self._to_money_decimal(annual_totals.get("akonto_total")),
        }
        totals["netto_total"] = (totals["netto_10"] + totals["netto_20"]).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        totals["ust_10"] = totals_brutto["ust_10"]
        totals["ust_20"] = totals_brutto["ust_20"]
        totals["ust_total"] = (totals["ust_10"] + totals["ust_20"]).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        totals["gross_10"] = totals_brutto["gross_10"]
        totals["gross_20"] = totals_brutto["gross_20"]
        totals["akonto_bk_brutto"] = totals_brutto["akonto_bk_brutto"]
        totals["akonto_hk_brutto"] = totals_brutto["akonto_hk_brutto"]
        totals["akonto_total_brutto"] = (
            totals["akonto_bk_brutto"] + totals["akonto_hk_brutto"]
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        totals["saldo_brutto_10"] = (
            totals["akonto_bk_brutto"] - totals["gross_10"]
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        totals["saldo_brutto_20"] = (
            totals["akonto_hk_brutto"] - totals["gross_20"]
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        totals["saldo_brutto"] = (totals["akonto_total_brutto"] - totals["gross_total"]).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        totals["saldo_netto"] = (totals["akonto_total"] - totals["netto_total"]).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        component_totals = {
            "bk_allg": self._to_money_decimal(
                allocations.get("bk_distribution", {}).get("distributed_sum")
            ),
            "wasser": self._to_money_decimal(allocations.get("water", {}).get("distributed_sum")),
            "allgemeinstrom": self._to_money_decimal(
                allocations.get("electricity_common", {}).get("distributed_sum")
            ),
            "warmwasser": self._to_money_decimal(
                allocations.get("hot_water", {}).get("distributed_sum")
            ),
            "heizung": self._to_money_decimal(allocations.get("heating", {}).get("distributed_sum")),
        }

        return {
            "rows": trace_rows,
            "totals": totals,
            "component_totals": component_totals,
        }

    @staticmethod
    def _sum_detail_rows(rows):
        total = Decimal("0.00")
        for row in rows:
            total += Decimal(str(row.get("amount") or "0.00"))
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _booking_reference_label(booking):
        unit = None
        if booking.mietervertrag_id and booking.mietervertrag and booking.mietervertrag.unit_id:
            unit = booking.mietervertrag.unit
        elif booking.einheit_id and booking.einheit:
            unit = booking.einheit
        if unit is None:
            return ""
        unit_name = (unit.name or "").strip()
        door_number = (unit.door_number or "").strip()
        if unit_name and door_number:
            return f"{unit_name} · {door_number}"
        return unit_name or door_number

    def _selected_property(self, properties):
        requested_property_id = (self.request.GET.get("liegenschaft") or "").strip()
        if requested_property_id:
            for property_obj in properties:
                if str(property_obj.pk) == requested_property_id:
                    return property_obj

        preferred_bhg14 = next(
            (
                property_obj
                for property_obj in properties
                if (property_obj.name or "").strip().casefold() == "bhg14"
            ),
            None,
        )
        if preferred_bhg14:
            return preferred_bhg14
        if properties:
            return properties[0]
        return None

    def _available_years_for_property(self, selected_property):
        if selected_property is None:
            return []

        belege_years = set(
            BetriebskostenBeleg.objects.filter(
                liegenschaft=selected_property
            ).values_list("datum__year", flat=True)
        )
        booking_years = set(
            Buchung.objects.filter(
                Q(mietervertrag__unit__property=selected_property)
                | Q(einheit__property=selected_property)
            )
            .filter(
                Q(
                    typ=Buchung.Typ.SOLL,
                    kategorie__in=[Buchung.Kategorie.BK, Buchung.Kategorie.HK],
                )
                | Q(
                    typ=Buchung.Typ.IST,
                    kategorie__in=[
                        Buchung.Kategorie.BK,
                        Buchung.Kategorie.HK,
                        Buchung.Kategorie.ZAHLUNG,
                    ],
                )
            )
            .values_list("datum__year", flat=True)
        )
        years = sorted(
            {
                int(year_value)
                for year_value in belege_years.union(booking_years)
                if year_value is not None
            }
        )
        return years

    def _selected_year(self, year_choices):
        current_year = timezone.localdate().year
        raw_year = (self.request.GET.get("jahr") or "").strip()
        requested_year = None
        if raw_year.isdigit():
            requested_year = int(raw_year)
            if not (2000 <= requested_year <= 2100):
                requested_year = None

        if requested_year is not None and requested_year in year_choices:
            return requested_year
        if requested_year is None and current_year in year_choices:
            return current_year
        if year_choices:
            return year_choices[-1]
        return current_year

    @staticmethod
    def _to_money_decimal(value):
        return Decimal(str(value or "0.00")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    @classmethod
    def _deserialize_bk_allg(cls, data):
        rows = []
        for row in data.get("rows", []):
            rows.append(
                {
                    "unit_id": row.get("unit_id"),
                    "label": row.get("label", ""),
                    "bk_anteil": cls._to_money_decimal(row.get("bk_anteil")),
                    "cost_share": cls._to_money_decimal(row.get("cost_share")),
                }
            )
        return {
            "rows": rows,
            "original_sum": cls._to_money_decimal(data.get("original_sum")),
            "distributed_sum": cls._to_money_decimal(data.get("distributed_sum")),
            "rounding_diff": cls._to_money_decimal(data.get("rounding_diff")),
            "has_source_costs": bool(data.get("has_source_costs")),
            "has_distribution_rows": bool(data.get("has_distribution_rows")),
            "strategy": data.get("strategy", "operating_cost_share"),
            "strategy_label": data.get("strategy_label", "BK-Anteil"),
        }


class AnnualStatementRunListView(TemplateView):
    template_name = "webapp/annual_statement_run_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        properties = list(Property.objects.order_by("name"))
        runs = (
            Abrechnungslauf.objects.select_related("liegenschaft")
            .annotate(letter_count=Count("schreiben"))
            .order_by("-jahr", "liegenschaft__name")
        )

        selected_property = None
        selected_property_id = (self.request.GET.get("liegenschaft") or "").strip()
        if selected_property_id.isdigit():
            selected_property = next(
                (item for item in properties if str(item.pk) == selected_property_id),
                None,
            )
        selected_year_raw = (self.request.GET.get("jahr") or "").strip()
        selected_year = int(selected_year_raw) if selected_year_raw.isdigit() else None

        if selected_property is not None:
            runs = runs.filter(liegenschaft=selected_property)
        if selected_year is not None:
            runs = runs.filter(jahr=selected_year)

        context["properties"] = properties
        context["runs"] = list(runs)
        context["selected_property_id"] = selected_property_id
        context["selected_year"] = selected_year_raw
        return context


class AnnualStatementRunEnsureView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        property_id = (request.GET.get("liegenschaft") or "").strip()
        year_raw = (request.GET.get("jahr") or "").strip()

        if not property_id.isdigit() or not year_raw.isdigit():
            messages.error(request, "Bitte Liegenschaft und Jahr auswählen.")
            return redirect("annual_statement_run_list")

        property_obj = get_object_or_404(Property, pk=int(property_id))
        year = int(year_raw)
        if year < 2000 or year > 2100:
            messages.error(request, "Ungültiges Jahr.")
            return redirect("annual_statement_run_list")

        run = AnnualStatementRunService.ensure_run(property_obj=property_obj, year=year)
        AnnualStatementRunService(run=run).ensure_letters()
        return redirect("annual_statement_run_detail", pk=run.pk)


class AnnualStatementRunDetailView(DetailView):
    model = Abrechnungslauf
    template_name = "webapp/annual_statement_run_detail.html"
    context_object_name = "run"

    def get_queryset(self):
        return Abrechnungslauf.objects.select_related("liegenschaft")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = AnnualStatementRunService(run=self.object)
        service.ensure_letters()

        letters = list(
            self.object.schreiben.select_related("mietervertrag", "einheit", "pdf_datei")
            .prefetch_related("mietervertrag__tenants")
            .order_by("einheit__door_number", "einheit__name", "mietervertrag_id")
        )
        sequence_numbers = service._sequence_numbers_for_letters(letters=letters)
        rows = []
        for letter in letters:
            payload = service.payload_for_letter(
                letter=letter,
                sequence_number=sequence_numbers.get(letter.id),
            )
            rows.append(
                {
                    "letter": letter,
                    "payload": payload,
                    "preview_url": reverse(
                        "annual_statement_letter_preview",
                        kwargs={"run_pk": self.object.pk, "pk": letter.pk},
                    ),
                }
            )

        context["letter_rows"] = rows
        context["create_zip_url"] = reverse(
            "annual_statement_run_generate_letters",
            kwargs={"pk": self.object.pk},
        )
        context["delete_url"] = reverse(
            "annual_statement_run_delete",
            kwargs={"pk": self.object.pk},
        )
        context["note_update_url"] = reverse(
            "annual_statement_run_update_note",
            kwargs={"pk": self.object.pk},
        )
        context["apply_url"] = reverse(
            "annual_statement_run_apply",
            kwargs={"pk": self.object.pk},
        )
        context["next_number_suggestion"] = AnnualStatementRunService.next_letter_number_suggestion()
        context["weasyprint_available"] = AnnualStatementPdfService.weasyprint_available()
        can_apply, apply_block_reason = service.apply_readiness()
        context["can_apply"] = can_apply
        context["apply_block_reason"] = apply_block_reason
        return context


class AnnualStatementRunNoteUpdateView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        run = get_object_or_404(Abrechnungslauf, pk=kwargs["pk"])
        raw_number = (request.POST.get("brief_nummer_start") or "").strip()
        parsed_number = None
        if raw_number:
            if not raw_number.isdigit() or int(raw_number) <= 0:
                messages.error(request, "Startnummer muss eine positive Zahl sein.")
                return redirect("annual_statement_run_detail", pk=run.pk)
            parsed_number = int(raw_number)
        run.brief_freitext = (request.POST.get("brief_freitext") or "").strip()
        run.brief_nummer_start = parsed_number
        run.save(update_fields=["brief_freitext", "brief_nummer_start", "updated_at"])
        if parsed_number:
            messages.success(request, f"Freitext und Startnummer {parsed_number} gespeichert.")
        else:
            messages.success(request, "Freitext gespeichert. Startnummer bitte noch bestätigen.")
        return redirect("annual_statement_run_detail", pk=run.pk)


class AnnualStatementRunDeleteView(View):
    http_method_names = ["get", "post"]
    template_name = "webapp/annual_statement_run_confirm_delete.html"
    valid_file_actions = {"keep", "archive", "delete"}

    @staticmethod
    def _pdf_files_for_run(*, run: Abrechnungslauf):
        letters = list(run.schreiben.select_related("pdf_datei"))
        pdf_by_id = {}
        for letter in letters:
            if letter.pdf_datei_id and letter.pdf_datei is not None:
                pdf_by_id[letter.pdf_datei_id] = letter.pdf_datei
        return letters, list(pdf_by_id.values())

    def get(self, request, *args, **kwargs):
        run = get_object_or_404(
            Abrechnungslauf.objects.select_related("liegenschaft"),
            pk=kwargs["pk"],
        )
        letters, pdf_files = self._pdf_files_for_run(run=run)
        return render(
            request,
            self.template_name,
            {
                "run": run,
                "letters_count": len(letters),
                "pdf_count": len(pdf_files),
                "default_file_action": "archive",
            },
        )

    def post(self, request, *args, **kwargs):
        run = get_object_or_404(
            Abrechnungslauf.objects.select_related("liegenschaft"),
            pk=kwargs["pk"],
        )
        file_action = (request.POST.get("file_action") or "archive").strip().lower()
        if file_action not in self.valid_file_actions:
            messages.error(request, "Ungültige Auswahl für die PDF-Behandlung.")
            return redirect("annual_statement_run_delete", pk=run.pk)

        _letters, pdf_files = self._pdf_files_for_run(run=run)
        if file_action == "archive":
            for pdf in pdf_files:
                DateiService.archive(user=None, datei=pdf)
        elif file_action == "delete":
            for pdf in pdf_files:
                DateiService.delete(user=None, datei=pdf)

        run_label = f"{run.liegenschaft.name} · {run.jahr}"
        run.delete()
        if file_action == "keep":
            messages.success(request, f"Brieflauf {run_label} wurde gelöscht. PDF-Dateien wurden beibehalten.")
        elif file_action == "archive":
            messages.success(request, f"Brieflauf {run_label} wurde gelöscht. {len(pdf_files)} PDF-Datei(en) wurden archiviert.")
        else:
            messages.success(request, f"Brieflauf {run_label} wurde gelöscht. {len(pdf_files)} PDF-Datei(en) wurden gelöscht.")
        return redirect("annual_statement_run_list")


class AnnualStatementLetterPreviewView(TemplateView):
    template_name = "webapp/annual_statement_letter_preview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        run = get_object_or_404(
            Abrechnungslauf.objects.select_related("liegenschaft"),
            pk=self.kwargs["run_pk"],
        )
        service = AnnualStatementRunService(run=run)
        service.ensure_letters()
        letter = get_object_or_404(
            run.schreiben.select_related("mietervertrag", "einheit", "pdf_datei").prefetch_related(
                "mietervertrag__tenants"
            ),
            pk=self.kwargs["pk"],
        )
        ordered_letters = list(
            run.schreiben.select_related("mietervertrag", "einheit", "pdf_datei")
            .prefetch_related("mietervertrag__tenants")
            .order_by("einheit__door_number", "einheit__name", "mietervertrag_id")
        )
        sequence_numbers = service._sequence_numbers_for_letters(letters=ordered_letters)
        payload = service.payload_for_letter(
            letter=letter,
            sequence_number=sequence_numbers.get(letter.id),
        )
        context["run"] = run
        context["letter"] = letter
        context["payload"] = payload
        return context


class AnnualStatementRunGenerateLettersView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        run = get_object_or_404(
            Abrechnungslauf.objects.select_related("liegenschaft"),
            pk=kwargs["pk"],
        )
        service = AnnualStatementRunService(run=run)
        try:
            zip_bytes, generated_count = service.generate_letters_zip()
        except RuntimeError as exc:
            messages.error(request, str(exc))
            return redirect("annual_statement_run_detail", pk=run.pk)
        response = HttpResponse(zip_bytes, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{service.build_zip_filename()}"'
        response["Content-Length"] = str(len(zip_bytes))
        response["X-Generated-Letters"] = str(generated_count)
        return response


class AnnualStatementRunApplyView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        run = get_object_or_404(
            Abrechnungslauf.objects.select_related("liegenschaft"),
            pk=kwargs["pk"],
        )
        if run.status == Abrechnungslauf.Status.APPLIED:
            messages.info(request, "Dieser BK-Lauf wurde bereits angewendet.")
            return redirect("annual_statement_run_detail", pk=run.pk)

        service = AnnualStatementRunService(run=run)
        can_apply, reason = service.apply_readiness(ensure_letters=True)
        if not can_apply:
            messages.error(request, reason)
            return redirect("annual_statement_run_detail", pk=run.pk)

        try:
            result = service.apply_run()
        except RuntimeError as exc:
            messages.error(request, str(exc))
            return redirect("annual_statement_run_detail", pk=run.pk)

        messages.success(
            request,
            (
                f"BK-Sollbuchungen angewendet. Verarbeitete Schreiben: {result['processed_letters']}, "
                f"BK-Buchungen: {result['created_bk']}, HK-Buchungen: {result['created_hk']}, "
                f"ohne Buchung (0,00): {result['skipped_zero']}."
            ),
        )
        return redirect("annual_statement_run_detail", pk=run.pk)


class VpiAdjustmentRunListView(TemplateView):
    template_name = "webapp/vpi_adjustment_run_list.html"
    formset_prefix = "index"

    def _build_formset(self, *, data=None):
        queryset = VpiIndexValue.objects.order_by("-month", "-id")
        if data is not None:
            return VpiIndexValueFormSet(data=data, queryset=queryset, prefix=self.formset_prefix)
        return VpiIndexValueFormSet(queryset=queryset, prefix=self.formset_prefix)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        formset = kwargs.get("formset") or self._build_formset()
        runs = (
            VpiAdjustmentRun.objects.select_related("index_value")
            .annotate(letter_count=Count("letters"))
            .order_by("-run_date", "-id")
        )
        pending_released_values = (
            VpiIndexValue.objects.filter(is_released=True)
            .exclude(adjustment_runs__isnull=False)
            .order_by("-month")
        )
        context["formset"] = formset
        context["runs"] = list(runs)
        context["pending_released_values"] = list(pending_released_values)
        context["today"] = timezone.localdate()
        return context

    def post(self, request, *args, **kwargs):
        formset = self._build_formset(data=request.POST)
        if formset.is_valid():
            instances = formset.save(commit=False)
            for instance in instances:
                instance.full_clean()
                instance.save()
            messages.success(request, "VPI-Indexwerte wurden gespeichert.")
            return redirect("vpi_adjustment_run_list")
        messages.error(request, "Bitte prüfen Sie die Eingaben der VPI-Indexwerte.")
        return self.render_to_response(self.get_context_data(formset=formset))


class VpiAdjustmentRunEnsureView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        index_id = (request.GET.get("index_id") or "").strip()
        run_date_raw = (request.GET.get("run_date") or "").strip()
        if not index_id.isdigit():
            messages.error(request, "Bitte einen freigegebenen VPI-Indexwert auswählen.")
            return redirect("vpi_adjustment_run_list")

        index_value = get_object_or_404(VpiIndexValue, pk=int(index_id))
        if not index_value.is_released:
            messages.error(request, "Der ausgewählte VPI-Indexwert ist noch nicht freigegeben.")
            return redirect("vpi_adjustment_run_list")

        run_date = timezone.localdate()
        if run_date_raw:
            try:
                run_date = datetime.strptime(run_date_raw, "%Y-%m-%d").date()
            except ValueError:
                messages.error(request, "Ungültiges Laufdatum. Erwartet: YYYY-MM-DD.")
                return redirect("vpi_adjustment_run_list")

        run = VpiAdjustmentRunService.ensure_run(index_value=index_value, run_date=run_date)
        VpiAdjustmentRunService(run=run).ensure_letters()
        return redirect("vpi_adjustment_run_detail", pk=run.pk)


class VpiAdjustmentRunDetailView(DetailView):
    model = VpiAdjustmentRun
    template_name = "webapp/vpi_adjustment_run_detail.html"
    context_object_name = "run"

    def get_queryset(self):
        return VpiAdjustmentRun.objects.select_related("index_value")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = VpiAdjustmentRunService(run=self.object)
        service.ensure_letters()

        letters = list(
            self.object.letters.select_related("lease", "unit", "pdf_datei")
            .prefetch_related("lease__tenants")
            .order_by("unit__door_number", "unit__name", "lease_id")
        )
        sequence_numbers = {}
        if self.object.brief_nummer_start and int(self.object.brief_nummer_start) > 0:
            sequence_numbers = service._sequence_numbers_for_letters(
                letters=letters,
                start_number=int(self.object.brief_nummer_start),
            )

        rows = []
        for letter in letters:
            rows.append(
                {
                    "letter": letter,
                    "payload": service.payload_for_letter(
                        letter=letter,
                        sequence_number=sequence_numbers.get(letter.id),
                    ),
                    "preview_url": reverse(
                        "vpi_adjustment_letter_preview",
                        kwargs={"run_pk": self.object.pk, "pk": letter.pk},
                    ),
                }
            )

        context["letter_rows"] = rows
        context["create_zip_url"] = reverse(
            "vpi_adjustment_run_generate_letters",
            kwargs={"pk": self.object.pk},
        )
        context["apply_url"] = reverse(
            "vpi_adjustment_run_apply",
            kwargs={"pk": self.object.pk},
        )
        context["note_update_url"] = reverse(
            "vpi_adjustment_run_update_note",
            kwargs={"pk": self.object.pk},
        )
        context["next_number_suggestion"] = VpiAdjustmentRunService.next_letter_number_suggestion()
        context["weasyprint_available"] = VpiAdjustmentPdfService.weasyprint_available()
        can_apply, apply_block_reason = service.apply_readiness()
        context["can_apply"] = can_apply
        context["apply_block_reason"] = apply_block_reason
        return context


class VpiAdjustmentRunNoteUpdateView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        run = get_object_or_404(VpiAdjustmentRun, pk=kwargs["pk"])
        raw_number = (request.POST.get("brief_nummer_start") or "").strip()
        parsed_number = None
        if raw_number:
            if not raw_number.isdigit() or int(raw_number) <= 0:
                messages.error(request, "Startnummer muss eine positive Zahl sein.")
                return redirect("vpi_adjustment_run_detail", pk=run.pk)
            parsed_number = int(raw_number)
        run.brief_freitext = (request.POST.get("brief_freitext") or "").strip()
        run.brief_nummer_start = parsed_number
        run.save(update_fields=["brief_freitext", "brief_nummer_start", "updated_at"])
        if parsed_number:
            messages.success(request, f"Freitext und Startnummer {parsed_number} gespeichert.")
        else:
            messages.success(request, "Freitext gespeichert. Startnummer bitte noch bestätigen.")
        return redirect("vpi_adjustment_run_detail", pk=run.pk)


class VpiAdjustmentLetterPreviewView(TemplateView):
    template_name = "webapp/vpi_adjustment_letter_preview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        run = get_object_or_404(
            VpiAdjustmentRun.objects.select_related("index_value"),
            pk=self.kwargs["run_pk"],
        )
        service = VpiAdjustmentRunService(run=run)
        service.ensure_letters()
        letter = get_object_or_404(
            run.letters.select_related("lease", "unit", "pdf_datei").prefetch_related("lease__tenants"),
            pk=self.kwargs["pk"],
        )
        ordered_letters = list(
            run.letters.select_related("lease", "unit")
            .order_by("unit__door_number", "unit__name", "lease_id")
        )
        sequence_numbers = {}
        if run.brief_nummer_start and int(run.brief_nummer_start) > 0:
            sequence_numbers = service._sequence_numbers_for_letters(
                letters=ordered_letters,
                start_number=int(run.brief_nummer_start),
            )
        payload = service.payload_for_letter(
            letter=letter,
            sequence_number=sequence_numbers.get(letter.id),
        )
        context["run"] = run
        context["letter"] = letter
        context["payload"] = payload
        return context


class VpiAdjustmentRunGenerateLettersView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        run = get_object_or_404(
            VpiAdjustmentRun.objects.select_related("index_value"),
            pk=kwargs["pk"],
        )
        service = VpiAdjustmentRunService(run=run)
        try:
            zip_bytes, generated_count = service.generate_letters_zip()
        except RuntimeError as exc:
            messages.error(request, str(exc))
            return redirect("vpi_adjustment_run_detail", pk=run.pk)
        response = HttpResponse(zip_bytes, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{service.build_zip_filename()}"'
        response["Content-Length"] = str(len(zip_bytes))
        response["X-Generated-Letters"] = str(generated_count)
        return response


class VpiAdjustmentRunApplyView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        run = get_object_or_404(
            VpiAdjustmentRun.objects.select_related("index_value"),
            pk=kwargs["pk"],
        )
        if run.status == VpiAdjustmentRun.Status.APPLIED:
            messages.info(request, "Dieser VPI-Lauf wurde bereits angewendet.")
            return redirect("vpi_adjustment_run_detail", pk=run.pk)

        service = VpiAdjustmentRunService(run=run)
        can_apply, reason = service.apply_readiness(ensure_letters=True)
        if not can_apply:
            messages.error(request, reason)
            return redirect("vpi_adjustment_run_detail", pk=run.pk)

        try:
            result = service.apply_run()
        except RuntimeError as exc:
            messages.error(request, str(exc))
            return redirect("vpi_adjustment_run_detail", pk=run.pk)

        messages.success(
            request,
            (
                f"VPI-Anpassung angewendet. Verträge aktualisiert: {result['updated_leases']}, "
                f"Nachverrechnungs-Buchungen: {result['catchup_bookings']}, "
                f"übersprungene Zeilen: {result['skipped_letters']}."
            ),
        )
        return redirect("vpi_adjustment_run_detail", pk=run.pk)


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attachments_panel"] = build_attachments_panel_context(
            self.request,
            self.object,
            title="Dateien zur Einheit",
        )
        return context


class UnitDeleteView(DeleteView):
    model = Unit
    template_name = "webapp/unit_confirm_delete.html"
    success_url = reverse_lazy("unit_list")
