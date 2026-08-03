# Generated manually for the independent Bookkeeping Phase 1 foundation.

import bookkeeping.storage_paths
import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Mandant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Name")),
                ("kurzname", models.CharField(max_length=40, unique=True, verbose_name="Kurzname")),
                ("steuerliche_id", models.CharField(blank=True, max_length=100, verbose_name="Steuerliche ID")),
                ("waehrung", models.CharField(default="EUR", max_length=3, verbose_name="Währung")),
                ("aktiv", models.BooleanField(default=True, verbose_name="Aktiv")),
                ("erstellt_am", models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")),
                ("aktualisiert_am", models.DateTimeField(auto_now=True, verbose_name="Aktualisiert am")),
            ],
            options={"verbose_name": "Mandant", "verbose_name_plural": "Mandanten", "ordering": ["name", "id"]},
        ),
        migrations.CreateModel(
            name="Bankkonto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "iban_normalisiert",
                    models.CharField(
                        max_length=34,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Die normalisierte IBAN darf nur Großbuchstaben und Ziffern enthalten.",
                                regex="^[A-Z0-9]{15,34}$",
                            )
                        ],
                        verbose_name="IBAN",
                    ),
                ),
                ("bezeichnung", models.CharField(max_length=255, verbose_name="Bezeichnung")),
                ("waehrung", models.CharField(default="EUR", max_length=3, verbose_name="Währung")),
                ("aktiv_von", models.DateField(blank=True, null=True, verbose_name="Aktiv von")),
                ("aktiv_bis", models.DateField(blank=True, null=True, verbose_name="Aktiv bis")),
                (
                    "mandant",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bankkonten", to="bookkeeping.mandant"),
                ),
            ],
            options={"verbose_name": "Bankkonto", "verbose_name_plural": "Bankkonten", "ordering": ["mandant__name", "bezeichnung", "id"]},
        ),
        migrations.CreateModel(
            name="Kostenstelle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=80, verbose_name="Code")),
                ("bezeichnung", models.CharField(max_length=255, verbose_name="Bezeichnung")),
                ("external_source", models.CharField(blank=True, max_length=80, verbose_name="Externe Quelle")),
                ("external_id", models.CharField(blank=True, max_length=120, verbose_name="Externe ID")),
                ("aktiv_von", models.DateField(blank=True, null=True, verbose_name="Aktiv von")),
                ("aktiv_bis", models.DateField(blank=True, null=True, verbose_name="Aktiv bis")),
                (
                    "mandant",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kostenstellen", to="bookkeeping.mandant"),
                ),
            ],
            options={"verbose_name": "Kostenstelle", "verbose_name_plural": "Kostenstellen", "ordering": ["mandant__name", "code", "id"]},
        ),
        migrations.CreateModel(
            name="KontenplanVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("bezeichnung", models.CharField(max_length=255, verbose_name="Bezeichnung")),
                ("gueltig_ab", models.DateField(verbose_name="Gültig ab")),
                ("vorlage_datei", models.FileField(upload_to=bookkeeping.storage_paths.kontenplan_vorlage_upload_to, verbose_name="Originalvorlage")),
                ("vorlage_dateiname", models.CharField(max_length=255, verbose_name="Originaldateiname")),
                ("vorlage_sha256", models.CharField(max_length=64, verbose_name="SHA-256")),
                ("importiert_am", models.DateTimeField(auto_now_add=True, verbose_name="Importiert am")),
                ("aktiv", models.BooleanField(default=True, verbose_name="Aktiv")),
                (
                    "mandant",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kontenplanversionen", to="bookkeeping.mandant"),
                ),
            ],
            options={"verbose_name": "Kontenplanversion", "verbose_name_plural": "Kontenplanversionen", "ordering": ["mandant__name", "-gueltig_ab", "-id"]},
        ),
        migrations.CreateModel(
            name="KontenplanEintrag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kategorie_text", models.CharField(max_length=255, verbose_name="Kategorie")),
                ("kontonummer", models.CharField(blank=True, max_length=80, verbose_name="Kontonummer")),
                ("bezeichnung", models.CharField(blank=True, max_length=255, verbose_name="Bezeichnung")),
                ("kontoart", models.CharField(blank=True, max_length=120, verbose_name="Kontoart")),
                ("kontoklasse", models.CharField(blank=True, max_length=120, verbose_name="Kontoklasse")),
                ("ust_stcode", models.CharField(blank=True, max_length=40, verbose_name="USt-Steuercode")),
                ("ust_prozent", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name="USt (%)")),
                ("aktiv", models.BooleanField(default=True, verbose_name="Aktiv")),
                (
                    "version",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="eintraege", to="bookkeeping.kontenplanversion"),
                ),
            ],
            options={"verbose_name": "Kontenplaneintrag", "verbose_name_plural": "Kontenplaneinträge", "ordering": ["kategorie_text", "id"]},
        ),
        migrations.CreateModel(
            name="AuditEreignis",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("objekt_typ", models.CharField(max_length=100, verbose_name="Objekttyp")),
                ("objekt_id", models.CharField(max_length=100, verbose_name="Objekt-ID")),
                ("aktion", models.CharField(max_length=100, verbose_name="Aktion")),
                ("vorher", models.JSONField(blank=True, default=dict, verbose_name="Vorher")),
                ("nachher", models.JSONField(blank=True, default=dict, verbose_name="Nachher")),
                ("zeitpunkt", models.DateTimeField(auto_now_add=True, verbose_name="Zeitpunkt")),
                ("correlation_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                (
                    "benutzer",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="bookkeeping_audit_ereignisse", to=settings.AUTH_USER_MODEL, verbose_name="Benutzer"),
                ),
                (
                    "mandant",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="audit_ereignisse", to="bookkeeping.mandant"),
                ),
            ],
            options={"verbose_name": "Audit-Ereignis", "verbose_name_plural": "Audit-Ereignisse", "ordering": ["-zeitpunkt", "-id"]},
        ),
        migrations.AddConstraint(model_name="bankkonto", constraint=models.UniqueConstraint(fields=("mandant", "iban_normalisiert"), name="bk_unique_mandant_iban")),
        migrations.AddConstraint(model_name="kostenstelle", constraint=models.UniqueConstraint(fields=("mandant", "code"), name="bk_unique_mandant_kostenstelle")),
        migrations.AddConstraint(model_name="kontenplanversion", constraint=models.UniqueConstraint(fields=("mandant", "vorlage_sha256"), name="bk_unique_mandant_vorlage_hash")),
        migrations.AddConstraint(model_name="kontenplanversion", constraint=models.UniqueConstraint(condition=Q(("aktiv", True)), fields=("mandant",), name="bk_one_active_kontenplan_per_mandant")),
        migrations.AddConstraint(model_name="kontenplaneintrag", constraint=models.UniqueConstraint(fields=("version", "kategorie_text"), name="bk_unique_version_kategorie")),
        migrations.AddIndex(model_name="auditereignis", index=models.Index(fields=["objekt_typ", "objekt_id"], name="bk_audit_object_idx")),
    ]
