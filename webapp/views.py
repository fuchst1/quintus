import json
import os
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from itertools import combinations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.db.models import DecimalField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.views.generic import DetailView, View
from .models import (
    BetriebskostenBeleg,
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
)
from .forms import (
    BankImportForm,
    BetriebskostenBelegForm,
    BuchungForm,
    DateiUploadForm,
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
from .services.files import DateiService
from .services.operating_cost_service import OperatingCostService


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
                "can_download": DateiService.can_download(user=request.user, datei=datei),
                "can_archive": DateiService.can_archive(user=request.user, datei=datei),
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
        context['stats'] = {
            'properties': Property.objects.count(),
            'units': Unit.objects.count(),
            'owners': Owner.objects.count(),
        }
        return context


class DateiUploadView(View):
    http_method_names = ["post"]
    form_class = DateiUploadForm

    def post(self, request, *args, **kwargs):
        next_url = request.POST.get("next") or reverse_lazy("dashboard")
        form = self.form_class(request.POST, request.FILES)
        if not form.is_valid():
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
            return redirect(next_url)

        try:
            datei = form.save()
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
            return redirect(next_url)

        messages.success(request, "Datei wurde hochgeladen.")
        if datei.duplicate_of_id:
            messages.warning(
                request,
                "Hinweis: Die Datei ist inhaltlich bereits vorhanden und wurde als Duplikat markiert.",
            )
        return redirect(next_url)


class DateiDownloadView(LoginRequiredMixin, View):
    http_method_names = ["get"]

    def get(self, request, pk, *args, **kwargs):
        datei = get_object_or_404(
            Datei.objects.select_related("uploaded_by").prefetch_related("zuordnungen__content_type"),
            pk=pk,
        )
        DateiService.prepare_download(user=request.user, datei=datei)
        if not datei.file:
            raise Http404("Datei wurde nicht gefunden.")

        download_name = datei.original_name or os.path.basename(datei.file.name or "")
        response = FileResponse(
            datei.file.open("rb"),
            as_attachment=True,
            filename=download_name,
        )
        response["Content-Type"] = datei.mime_type or "application/octet-stream"
        return response


class DateiPreviewView(LoginRequiredMixin, View):
    http_method_names = ["get"]

    def get(self, request, pk, *args, **kwargs):
        datei = get_object_or_404(
            Datei.objects.select_related("uploaded_by").prefetch_related("zuordnungen__content_type"),
            pk=pk,
        )
        DateiService.prepare_download(user=request.user, datei=datei)
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


class DateiArchiveView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk, *args, **kwargs):
        next_url = request.POST.get("next") or reverse_lazy("dashboard")
        datei = get_object_or_404(Datei, pk=pk)
        try:
            DateiService.archive(user=request.user, datei=datei)
        except PermissionDenied as exc:
            messages.error(request, str(exc))
            return redirect(next_url)

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
        context["active_leases"] = (
            self.queryset.filter(status=LeaseAgreement.Status.AKTIV).order_by(*self.unit_ordering)
        )
        context["ended_leases"] = (
            self.queryset.filter(status=LeaseAgreement.Status.BEENDET).order_by(*self.unit_ordering)
        )
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
            return bool(row.get("bk_property_id"))
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
                    "bk_art": row_defaults["bk_art"],
                    "bk_ust_prozent": row_defaults["bk_ust_prozent"],
                    "dismiss": row_defaults["dismiss"],
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
    defaults = {
        "booking_type": "miete" if Decimal(amount) > Decimal("0.00") else "bk",
        "bk_art": infer_bk_art_from_bank_text(partner_name, purpose),
        "bk_ust_prozent": "20.00",
        "bk_property_id": "",
        "dismiss": False,
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
        queryset = super().get_queryset()
        bank_transaktion_id = self.request.GET.get("bank_transaktion")
        if bank_transaktion_id:
            queryset = queryset.filter(bank_transaktion_id=bank_transaktion_id)
        return queryset


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


class BetriebskostenBelegListView(ListView):
    model = BetriebskostenBeleg
    template_name = "webapp/betriebskostenbeleg_list.html"
    context_object_name = "belege"
    queryset = BetriebskostenBeleg.objects.select_related("liegenschaft").order_by("-datum", "-id")


class BetriebskostenBelegCreateView(CreateView):
    model = BetriebskostenBeleg
    form_class = BetriebskostenBelegForm
    template_name = "webapp/betriebskostenbeleg_form.html"
    success_url = reverse_lazy("betriebskostenbeleg_list")


class BetriebskostenBelegUpdateView(UpdateView):
    model = BetriebskostenBeleg
    form_class = BetriebskostenBelegForm
    template_name = "webapp/betriebskostenbeleg_form.html"
    success_url = reverse_lazy("betriebskostenbeleg_list")


class BetriebskostenBelegDeleteView(DeleteView):
    model = BetriebskostenBeleg
    template_name = "webapp/betriebskostenbeleg_confirm_delete.html"
    success_url = reverse_lazy("betriebskostenbeleg_list")


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

        report = OperatingCostService(
            property=selected_property,
            year=selected_year,
        ).get_report_data()

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
        return context

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
