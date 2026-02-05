from django.contrib import admin

from .models import LeaseAgreement, Manager, Meter, MeterReading, Owner, Ownership, Property, Tenant, Unit


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
class LeaseAgreementAdmin(admin.ModelAdmin):
    list_display = ("unit", "status", "entry_date", "exit_date", "net_rent")
    list_filter = ("status", "index_type", "manager")
    search_fields = ("unit__name", "tenants__first_name", "tenants__last_name")


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
