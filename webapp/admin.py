from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    BankTransaktion,
    BetriebskostenBeleg,
    Buchung,
    LeaseAgreement,
    Manager,
    Meter,
    MeterReading,
    Owner,
    Ownership,
    Property,
    Tenant,
    Unit,
)


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
    list_display = ("company_name", "contact_person", "email", "phone", "tax_mode")
    search_fields = ("company_name", "contact_person", "email", "phone", "website")
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
    list_display = ("datum", "mietervertrag", "kategorie", "typ", "brutto")
    list_filter = ("typ", "kategorie", "datum")


@admin.register(BetriebskostenBeleg)
class BetriebskostenBelegAdmin(admin.ModelAdmin):
    list_display = ("datum", "liegenschaft", "bk_art", "netto", "ust_prozent", "brutto")
    list_filter = ("bk_art", "datum", "liegenschaft")
    search_fields = ("buchungstext", "lieferant_name", "iban", "import_referenz")
