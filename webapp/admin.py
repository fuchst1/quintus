from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.contrib import admin, messages
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    Abrechnungslauf,
    Abrechnungsschreiben,
    BankTransaktion,
    BetriebskostenBeleg,
    BetriebskostenGruppe,
    Buchung,
    Datei,
    DateiOperationLog,
    DateiZuordnung,
    LeaseAgreement,
    Manager,
    Meter,
    MeterReading,
    Owner,
    Ownership,
    Property,
    Tenant,
    Unit,
    ReminderRuleConfig,
    ReminderEmailLog,
    VpiIndexValue,
    VpiAdjustmentRun,
    VpiAdjustmentLetter,
)
from .services.files import DateiService


class OwnershipInline(admin.TabularInline):
    model = Ownership
    extra = 0


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "manager", "city", "zip_code", "street_address", "heating_share_percent")
    search_fields = ("name", "city", "zip_code", "street_address")
    inlines = (OwnershipInline,)


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = ("company_name", "contact_person", "email", "phone", "account_number", "tax_mode")
    search_fields = ("company_name", "contact_person", "email", "phone", "website", "account_number")
    list_filter = ("tax_mode",)


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "property",
        "unit_type",
        "door_number",
        "usable_area",
        "operating_cost_share",
    )
    list_filter = ("unit_type", "property")
    search_fields = ("name", "door_number", "property__name")


@admin.register(Owner)
class OwnerAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone")
    search_fields = ("name", "email", "phone")
    inlines = (OwnershipInline,)


@admin.register(Ownership)
class OwnershipAdmin(admin.ModelAdmin):
    list_display = ("property", "owner", "share_percent")
    search_fields = ("property__name", "owner__name")
    list_filter = ("property", "owner")


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("salutation", "first_name", "last_name", "email", "phone")
    search_fields = ("first_name", "last_name", "email", "phone")
    list_filter = ("salutation",)


@admin.register(LeaseAgreement)
class LeaseAgreementAdmin(SimpleHistoryAdmin):
    list_display = ("unit", "status", "entry_date", "exit_date", "net_rent")
    list_filter = ("status", "index_type", "manager")
    search_fields = ("unit__name", "tenants__first_name", "tenants__last_name")
    history_list_display = ("status", "entry_date", "exit_date", "net_rent", "history_user", "history_date")


@admin.register(Meter)
class MeterAdmin(admin.ModelAdmin):
    list_display = ("meter_number", "meter_type", "kind", "property", "unit", "is_main_meter")
    list_filter = ("meter_type", "kind", "property", "is_main_meter")
    search_fields = ("meter_number", "property__name", "unit__name")


@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ("meter", "date", "value")
    list_filter = ("date",)
    search_fields = ("meter__meter_number",)


@admin.register(BankTransaktion)
class BankTransaktionAdmin(admin.ModelAdmin):
    list_display = ("buchungsdatum", "partner_name", "iban", "betrag", "referenz_nummer")
    search_fields = ("partner_name", "iban", "referenz_nummer", "verwendungszweck")
    list_filter = ("buchungsdatum",)


@admin.register(Buchung)
class BuchungAdmin(SimpleHistoryAdmin):
    class BuchungAdminForm(forms.ModelForm):
        class Meta:
            model = Buchung
            fields = "__all__"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if "brutto" in self.fields:
                self.fields["brutto"].disabled = True

        def clean(self):
            cleaned_data = super().clean()
            netto = cleaned_data.get("netto")
            ust_prozent = cleaned_data.get("ust_prozent")
            if netto is None or ust_prozent is None:
                return cleaned_data
            computed = (
                netto + (netto * ust_prozent / Decimal("100"))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cleaned_data["brutto"] = computed
            self.instance.brutto = computed
            return cleaned_data

    form = BuchungAdminForm
    list_display = (
        "datum",
        "mietervertrag",
        "kategorie",
        "typ",
        "is_settlement_adjustment",
        "brutto",
    )
    list_filter = ("typ", "kategorie", "is_settlement_adjustment", "datum")


@admin.register(BetriebskostenBeleg)
class BetriebskostenBelegAdmin(admin.ModelAdmin):
    list_display = (
        "datum",
        "liegenschaft",
        "ausgabengruppe",
        "bk_art",
        "netto",
        "ust_prozent",
        "brutto",
    )
    list_filter = ("ausgabengruppe", "bk_art", "datum", "liegenschaft")
    search_fields = ("buchungstext", "lieferant_name", "iban", "import_referenz")


@admin.register(BetriebskostenGruppe)
class BetriebskostenGruppeAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order", "is_active", "system_key")
    list_filter = ("is_active",)
    search_fields = ("name", "system_key")
    ordering = ("sort_order", "name", "id")


@admin.register(Datei)
class DateiAdmin(admin.ModelAdmin):
    list_display = (
        "original_name",
        "kategorie",
        "is_archived",
        "mime_type",
        "size_bytes",
        "archived_at",
        "duplicate_of",
        "created_at",
    )
    list_filter = ("kategorie", "is_archived", "created_at", "archived_at")
    search_fields = ("original_name", "beschreibung", "checksum_sha256")
    readonly_fields = (
        "original_name",
        "mime_type",
        "size_bytes",
        "checksum_sha256",
        "duplicate_of",
        "created_at",
        "archived_at",
        "archived_by",
    )
    actions = ("archive_selected", "restore_selected")

    @admin.action(description="Ausgewählte Dateien archivieren")
    def archive_selected(self, request, queryset):
        updated = 0
        for datei in queryset:
            if datei.is_archived:
                continue
            DateiService.archive(user=None, datei=datei)
            updated += 1
        if updated:
            self.message_user(request, f"{updated} Datei(en) archiviert.", level=messages.SUCCESS)
        else:
            self.message_user(
                request,
                "Keine Dateien archiviert (bereits archiviert).",
                level=messages.WARNING,
            )

    @admin.action(description="Ausgewählte Dateien wiederherstellen")
    def restore_selected(self, request, queryset):
        updated = 0
        for datei in queryset:
            if not datei.is_archived:
                continue
            DateiService.restore(user=None, datei=datei)
            updated += 1
        if updated:
            self.message_user(
                request,
                f"{updated} Datei(en) wiederhergestellt.",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "Keine Dateien wiederhergestellt.",
                level=messages.WARNING,
            )


@admin.register(DateiZuordnung)
class DateiZuordnungAdmin(admin.ModelAdmin):
    list_display = (
        "datei",
        "content_type",
        "object_id",
        "created_at",
    )
    list_filter = (
        "content_type",
        "created_at",
    )
    search_fields = ("datei__original_name",)


@admin.register(DateiOperationLog)
class DateiOperationLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "operation",
        "success",
        "actor",
        "datei_name",
        "content_type",
        "object_id",
    )
    list_filter = ("operation", "success", "created_at")
    search_fields = ("datei_name", "detail", "actor__username")
    readonly_fields = (
        "created_at",
        "operation",
        "success",
        "actor",
        "datei",
        "datei_name",
        "content_type",
        "object_id",
        "detail",
    )


@admin.register(ReminderRuleConfig)
class ReminderRuleConfigAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "lead_months", "is_active", "sort_order", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "title")
    ordering = ("sort_order", "code")


@admin.register(ReminderEmailLog)
class ReminderEmailLogAdmin(admin.ModelAdmin):
    list_display = ("period_start", "recipient_email", "rule_code", "lease", "due_date", "sent_at")
    list_filter = ("period_start", "rule_code", "sent_at")
    search_fields = ("recipient_email", "rule_code", "lease__unit__name", "lease__unit__property__name")
    readonly_fields = ("period_start", "recipient_email", "rule_code", "lease", "due_date", "sent_at")
    ordering = ("-sent_at",)


@admin.register(VpiIndexValue)
class VpiIndexValueAdmin(admin.ModelAdmin):
    list_display = ("month", "index_value", "is_released", "released_at", "updated_at")
    list_filter = ("is_released", "released_at")
    search_fields = ("month", "note")
    ordering = ("-month",)


@admin.register(VpiAdjustmentRun)
class VpiAdjustmentRunAdmin(admin.ModelAdmin):
    list_display = (
        "index_value",
        "run_date",
        "status",
        "brief_nummer_start",
        "applied_at",
        "created_at",
    )
    list_filter = ("status", "run_date")
    search_fields = ("index_value__month",)
    ordering = ("-run_date", "-id")


@admin.register(VpiAdjustmentLetter)
class VpiAdjustmentLetterAdmin(admin.ModelAdmin):
    list_display = (
        "run",
        "laufende_nummer",
        "lease",
        "effective_date",
        "old_hmz_net",
        "new_hmz_net",
        "catchup_gross_total",
        "generated_at",
        "applied_at",
    )
    list_filter = ("run__run_date", "generated_at", "applied_at")
    search_fields = ("lease__unit__name", "lease__unit__property__name", "skip_reason")
    ordering = ("run__run_date", "unit__name", "lease_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Abrechnungslauf)
class AbrechnungslaufAdmin(admin.ModelAdmin):
    list_display = (
        "liegenschaft",
        "jahr",
        "status",
        "brief_nummer_start",
        "applied_at",
        "brief_freitext",
        "created_at",
        "updated_at",
    )
    list_filter = ("jahr", "liegenschaft", "status")
    search_fields = ("liegenschaft__name",)


@admin.register(Abrechnungsschreiben)
class AbrechnungsschreibenAdmin(admin.ModelAdmin):
    list_display = (
        "lauf",
        "laufende_nummer",
        "mietervertrag",
        "einheit",
        "settlement_booking_bk",
        "settlement_booking_hk",
        "applied_at",
        "pdf_datei",
        "generated_at",
    )
    list_filter = ("lauf__jahr", "lauf__liegenschaft", "applied_at")
    search_fields = (
        "mietervertrag__unit__name",
        "mietervertrag__tenants__first_name",
        "mietervertrag__tenants__last_name",
    )
