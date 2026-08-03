from django.contrib import admin

from bookkeeping.models import AuditEreignis, Bankkonto, KontenplanEintrag, KontenplanVersion, Kostenstelle, Mandant


@admin.register(Mandant)
class MandantAdmin(admin.ModelAdmin):
    list_display = ("name", "kurzname", "waehrung", "aktiv")
    search_fields = ("name", "kurzname", "steuerliche_id")


@admin.register(Bankkonto)
class BankkontoAdmin(admin.ModelAdmin):
    list_display = ("bezeichnung", "mandant", "iban_normalisiert", "waehrung")
    search_fields = ("bezeichnung", "iban_normalisiert")
    list_filter = ("mandant", "waehrung")


@admin.register(Kostenstelle)
class KostenstelleAdmin(admin.ModelAdmin):
    list_display = ("code", "bezeichnung", "mandant", "aktiv_von", "aktiv_bis")
    search_fields = ("code", "bezeichnung", "external_id")
    list_filter = ("mandant",)


class KontenplanEintragInline(admin.TabularInline):
    model = KontenplanEintrag
    extra = 0
    can_delete = False
    readonly_fields = ("kategorie_text", "kontonummer", "bezeichnung", "kontoart", "kontoklasse", "ust_stcode")


@admin.register(KontenplanVersion)
class KontenplanVersionAdmin(admin.ModelAdmin):
    list_display = ("bezeichnung", "mandant", "gueltig_ab", "aktiv", "importiert_am")
    list_filter = ("mandant", "aktiv")
    search_fields = ("bezeichnung", "vorlage_dateiname", "vorlage_sha256")
    inlines = (KontenplanEintragInline,)


@admin.register(AuditEreignis)
class AuditEreignisAdmin(admin.ModelAdmin):
    list_display = ("zeitpunkt", "aktion", "objekt_typ", "objekt_id", "mandant", "benutzer")
    list_filter = ("mandant", "aktion", "objekt_typ")
    search_fields = ("objekt_id", "correlation_id")
    readonly_fields = ("mandant", "objekt_typ", "objekt_id", "aktion", "vorher", "nachher", "benutzer", "zeitpunkt", "correlation_id")
