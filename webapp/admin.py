from django.contrib import admin

from .models import Owner, Ownership, Property, Unit


class OwnershipInline(admin.TabularInline):
    model = Ownership
    extra = 0


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "zip_code", "street_address", "heating_share_percent")
    search_fields = ("name", "city", "zip_code", "street_address")
    inlines = (OwnershipInline,)


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
