from django.db import migrations


def seed_immo_fuchs_kg(apps, schema_editor):
    Mandant = apps.get_model("bookkeeping", "Mandant")
    Mandant.objects.get_or_create(
        kurzname="IFKG",
        defaults={"name": "Immo-Fuchs KG", "waehrung": "EUR", "aktiv": True},
    )


def unseed_immo_fuchs_kg(apps, schema_editor):
    Mandant = apps.get_model("bookkeeping", "Mandant")
    Mandant.objects.filter(
        kurzname="IFKG",
        bankkonten__isnull=True,
        kostenstellen__isnull=True,
        kontenplanversionen__isnull=True,
        audit_ereignisse__isnull=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("bookkeeping", "0001_initial")]

    operations = [migrations.RunPython(seed_immo_fuchs_kg, unseed_immo_fuchs_kg)]
