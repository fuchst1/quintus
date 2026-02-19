from __future__ import annotations

import io
import json
import os
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from webapp.models import (
    Abrechnungsschreiben,
    BankTransaktion,
    Buchung,
    Datei,
    DateiZuordnung,
    LeaseAgreement,
    ReminderEmailLog,
    VpiAdjustmentLetter,
)
from webapp.services.files import DateiService


@dataclass(frozen=True)
class HistoryDocumentEntry:
    datei: Datei
    archive_name: str
    source_labels: tuple[str, ...]


class LeaseHistoryPackageService:
    DESCRIPTION_PREFIX = "Historie-Paket Mietvertrag #"

    def __init__(self, *, lease: LeaseAgreement):
        self.lease = lease

    def build_zip_filename(self) -> str:
        property_slug = slugify(self._property_name) or "liegenschaft"
        unit_slug = slugify(self._unit_name) or "einheit"
        timestamp = timezone.localtime(timezone.now()).strftime("%Y%m%d-%H%M%S")
        return f"Historie_{property_slug}_{unit_slug}_MV{self.lease.pk}_{timestamp}.zip"

    def generate_and_store_latest(self, *, trigger: str) -> tuple[Datei, bytes, dict[str, Any]]:
        zip_bytes, summary = self.build_zip_bytes(trigger=trigger)
        filename = self.build_zip_filename()
        description = (
            f"{self._description_prefix()} "
            f"({timezone.localtime(timezone.now()):%d.%m.%Y %H:%M}, Trigger: {trigger})"
        )

        with transaction.atomic():
            self._archive_previous_packages()

            file_obj = ContentFile(zip_bytes, name=filename)
            datei = Datei(
                file=file_obj,
                original_name=filename,
                kategorie=Datei.Kategorie.DOKUMENT,
                beschreibung=description,
                uploaded_by=None,
            )
            datei.set_upload_context(content_object=self.lease)
            datei.full_clean()
            datei.save()

            DateiZuordnung.objects.create(
                datei=datei,
                content_type=ContentType.objects.get_for_model(self.lease),
                object_id=self.lease.pk,
                created_by=None,
            )

        summary["datei_id"] = datei.pk
        summary["filename"] = filename
        return datei, zip_bytes, summary

    def build_zip_bytes(self, *, trigger: str) -> tuple[bytes, dict[str, Any]]:
        generated_at = timezone.localtime(timezone.now())
        (
            document_entries,
            annual_letters,
            vpi_letters,
        ) = self._collect_documents_and_letter_rows()
        db_payloads = self._build_db_payloads(
            document_entries=document_entries,
            annual_letters=annual_letters,
            vpi_letters=vpi_letters,
            generated_at=generated_at,
            trigger=trigger,
        )

        missing_files: list[dict[str, Any]] = []
        written_documents = 0
        documents_written_meta: list[dict[str, Any]] = []

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative_path, payload in db_payloads.items():
                archive.writestr(
                    relative_path,
                    json.dumps(self._json_ready(payload), ensure_ascii=False, indent=2),
                )

            for entry in document_entries:
                try:
                    content = self._read_file_bytes(entry.datei)
                except (OSError, ValueError) as exc:
                    missing_files.append(
                        {
                            "datei_id": entry.datei.pk,
                            "original_name": entry.datei.original_name,
                            "archive_name": entry.archive_name,
                            "error": str(exc),
                        }
                    )
                    continue

                archive.writestr(f"documents/{entry.archive_name}", content)
                written_documents += 1
                documents_written_meta.append(
                    {
                        "datei_id": entry.datei.pk,
                        "archive_name": entry.archive_name,
                        "source_labels": list(entry.source_labels),
                    }
                )

            summary_html = self._summary_html(
                generated_at=generated_at,
                trigger=trigger,
                document_entries=document_entries,
                written_documents=written_documents,
                missing_files=missing_files,
            )
            archive.writestr("summary.html", summary_html)

            manifest = {
                "lease_id": self.lease.pk,
                "generated_at": generated_at.isoformat(),
                "trigger": trigger,
                "property_name": self._property_name,
                "unit_name": self._unit_name,
                "manager_name": self._manager_name,
                "written_document_count": written_documents,
                "missing_file_count": len(missing_files),
                "missing_files": missing_files,
                "documents": documents_written_meta,
                "db_payloads": sorted(db_payloads.keys()),
            }
            archive.writestr(
                "meta/manifest.json",
                json.dumps(self._json_ready(manifest), ensure_ascii=False, indent=2),
            )

        summary = {
            "lease_id": self.lease.pk,
            "document_count": written_documents,
            "missing_file_count": len(missing_files),
        }
        return buffer.getvalue(), summary

    @property
    def _property_name(self) -> str:
        if self.lease.unit and self.lease.unit.property:
            return str(self.lease.unit.property.name or "")
        return "—"

    @property
    def _unit_name(self) -> str:
        if self.lease.unit:
            return str(self.lease.unit.name or "")
        return "—"

    @property
    def _manager_name(self) -> str:
        manager = self.lease.manager
        if manager is None and self.lease.unit and self.lease.unit.property:
            manager = self.lease.unit.property.manager
        if manager is None:
            return "—"
        return str(manager.company_name or manager.contact_person or manager.pk)

    def _description_prefix(self) -> str:
        return f"{self.DESCRIPTION_PREFIX}{self.lease.pk}"

    def _archive_previous_packages(self) -> None:
        lease_content_type = ContentType.objects.get_for_model(self.lease)
        old_package_ids = list(
            DateiZuordnung.objects.filter(
                content_type=lease_content_type,
                object_id=self.lease.pk,
                datei__beschreibung__startswith=self._description_prefix(),
                datei__is_archived=False,
            )
            .values_list("datei_id", flat=True)
            .distinct()
        )
        for datei in Datei.objects.filter(pk__in=old_package_ids):
            DateiService.archive(user=None, datei=datei)

    def _collect_documents_and_letter_rows(
        self,
    ) -> tuple[list[HistoryDocumentEntry], list[dict[str, Any]], list[dict[str, Any]]]:
        annual_letters = list(
            Abrechnungsschreiben.objects.filter(mietervertrag=self.lease)
            .select_related("lauf", "einheit", "pdf_datei")
            .order_by("lauf__jahr", "id")
            .values(
                "id",
                "lauf_id",
                "lauf__jahr",
                "mietervertrag_id",
                "einheit_id",
                "pdf_datei_id",
                "generated_at",
                "laufende_nummer",
                "applied_at",
                "created_at",
                "updated_at",
            )
        )
        annual_letter_pdf_ids = {int(row["pdf_datei_id"]) for row in annual_letters if row.get("pdf_datei_id")}

        vpi_letters = list(
            VpiAdjustmentLetter.objects.filter(lease=self.lease)
            .select_related("run", "run__index_value", "unit", "pdf_datei")
            .order_by("run__run_date", "id")
            .values(
                "id",
                "run_id",
                "run__run_date",
                "run__status",
                "run__index_value_id",
                "run__index_value__month",
                "lease_id",
                "unit_id",
                "effective_date",
                "old_index_value",
                "new_index_value",
                "factor",
                "old_hmz_net",
                "new_hmz_net",
                "delta_hmz_net",
                "catchup_months",
                "catchup_net_total",
                "catchup_tax_percent",
                "catchup_gross_total",
                "skip_reason",
                "pdf_datei_id",
                "generated_at",
                "laufende_nummer",
                "catchup_booking_id",
                "applied_at",
                "created_at",
                "updated_at",
            )
        )
        vpi_letter_pdf_ids = {int(row["pdf_datei_id"]) for row in vpi_letters if row.get("pdf_datei_id")}

        lease_content_type = ContentType.objects.get_for_model(self.lease)
        tenant_content_type = ContentType.objects.get_for_model(self.lease.tenants.model)
        tenant_ids = list(self.lease.tenants.values_list("pk", flat=True))

        assignment_queryset = (
            DateiZuordnung.objects.filter(
                Q(content_type=lease_content_type, object_id=self.lease.pk)
                | Q(content_type=tenant_content_type, object_id__in=tenant_ids)
            )
            .select_related("datei", "content_type")
            .order_by("id")
        )

        files_by_id: dict[int, Datei] = {}
        sources_by_file_id: dict[int, set[str]] = {}

        for assignment in assignment_queryset:
            datei = assignment.datei
            if datei is None or self._is_history_package_file(datei):
                continue
            files_by_id[datei.pk] = datei
            if assignment.content_type_id == lease_content_type.id:
                source = f"Mietvertrag #{assignment.object_id}"
            elif assignment.content_type_id == tenant_content_type.id:
                source = f"Mieter #{assignment.object_id}"
            else:
                source = f"{assignment.content_type.model} #{assignment.object_id}"
            sources_by_file_id.setdefault(datei.pk, set()).add(source)

        if annual_letter_pdf_ids:
            for datei in Datei.objects.filter(pk__in=annual_letter_pdf_ids):
                if self._is_history_package_file(datei):
                    continue
                files_by_id[datei.pk] = datei
                sources_by_file_id.setdefault(datei.pk, set()).add("BK-Schreiben")

        if vpi_letter_pdf_ids:
            for datei in Datei.objects.filter(pk__in=vpi_letter_pdf_ids):
                if self._is_history_package_file(datei):
                    continue
                files_by_id[datei.pk] = datei
                sources_by_file_id.setdefault(datei.pk, set()).add("VPI-Schreiben")

        entries: list[HistoryDocumentEntry] = []
        for datei_id in sorted(files_by_id):
            datei = files_by_id[datei_id]
            entries.append(
                HistoryDocumentEntry(
                    datei=datei,
                    archive_name=self._safe_document_name(datei),
                    source_labels=tuple(sorted(sources_by_file_id.get(datei_id, set()))),
                )
            )

        return entries, annual_letters, vpi_letters

    def _build_db_payloads(
        self,
        *,
        document_entries: list[HistoryDocumentEntry],
        annual_letters: list[dict[str, Any]],
        vpi_letters: list[dict[str, Any]],
        generated_at: datetime,
        trigger: str,
    ) -> dict[str, Any]:
        historical_lease_model = apps.get_model("webapp", "HistoricalLeaseAgreement")
        historical_lease_tenants_model = apps.get_model("webapp", "HistoricalLeaseAgreement_tenants")
        historical_buchung_model = apps.get_model("webapp", "HistoricalBuchung")

        booking_fields = [
            "id",
            "mietervertrag_id",
            "einheit_id",
            "bank_transaktion_id",
            "typ",
            "kategorie",
            "buchungstext",
            "datum",
            "netto",
            "ust_prozent",
            "brutto",
            "is_settlement_adjustment",
            "storniert_von_id",
        ]
        booking_rows = list(
            Buchung.objects.filter(mietervertrag=self.lease)
            .order_by("datum", "id")
            .values(*booking_fields)
        )
        bank_transaction_ids = sorted(
            {
                int(row["bank_transaktion_id"])
                for row in booking_rows
                if row.get("bank_transaktion_id") is not None
            }
        )

        document_file_ids = [entry.datei.pk for entry in document_entries]
        history_fields = [field.name for field in historical_lease_model._meta.fields]
        history_tenant_fields = [field.name for field in historical_lease_tenants_model._meta.fields]
        history_booking_fields = [field.name for field in historical_buchung_model._meta.fields]

        return {
            "db/leaseagreement.json": LeaseAgreement.objects.filter(pk=self.lease.pk).values(
                "id",
                "unit_id",
                "manager_id",
                "status",
                "entry_date",
                "exit_date",
                "index_type",
                "last_index_adjustment",
                "index_base_value",
                "net_rent",
                "operating_costs_net",
                "heating_costs_net",
                "deposit",
            ).first()
            or {},
            "db/tenants.json": list(
                self.lease.tenants.order_by("last_name", "first_name", "id").values(
                    "id",
                    "salutation",
                    "first_name",
                    "last_name",
                    "date_of_birth",
                    "email",
                    "phone",
                    "iban",
                    "notes",
                )
            ),
            "db/lease_history.json": list(
                historical_lease_model.objects.filter(id=self.lease.pk)
                .order_by("history_date", "history_id")
                .values(*history_fields)
            ),
            "db/lease_tenants_history.json": list(
                historical_lease_tenants_model.objects.filter(leaseagreement_id=self.lease.pk)
                .order_by("m2m_history_id")
                .values(*history_tenant_fields)
            ),
            "db/bookings.json": booking_rows,
            "db/bookings_history.json": list(
                historical_buchung_model.objects.filter(mietervertrag_id=self.lease.pk)
                .order_by("history_date", "history_id")
                .values(*history_booking_fields)
            ),
            "db/bank_transactions.json": list(
                BankTransaktion.objects.filter(pk__in=bank_transaction_ids).order_by("id").values(
                    "id",
                    "referenz_nummer",
                    "partner_name",
                    "iban",
                    "betrag",
                    "buchungsdatum",
                    "verwendungszweck",
                )
            ),
            "db/reminder_email_logs.json": list(
                ReminderEmailLog.objects.filter(lease=self.lease).order_by("sent_at", "id").values(
                    "id",
                    "period_start",
                    "recipient_email",
                    "rule_code",
                    "lease_id",
                    "due_date",
                    "sent_at",
                )
            ),
            "db/annual_statement_letters.json": annual_letters,
            "db/vpi_adjustment_letters.json": vpi_letters,
            "db/files_metadata.json": {
                "files": list(
                    Datei.objects.filter(pk__in=document_file_ids).order_by("id").values(
                        "id",
                        "original_name",
                        "file",
                        "mime_type",
                        "size_bytes",
                        "kategorie",
                        "beschreibung",
                        "created_at",
                        "is_archived",
                        "archived_at",
                        "duplicate_of_id",
                    )
                ),
                "assignments": list(
                    DateiZuordnung.objects.filter(datei_id__in=document_file_ids)
                    .order_by("id")
                    .values(
                        "id",
                        "datei_id",
                        "content_type_id",
                        "content_type__app_label",
                        "content_type__model",
                        "object_id",
                        "sichtbar_fuer_verwalter",
                        "sichtbar_fuer_eigentuemer",
                        "sichtbar_fuer_mieter",
                        "created_at",
                    )
                ),
            },
            "meta/package_context.json": {
                "lease_id": self.lease.pk,
                "trigger": trigger,
                "generated_at": generated_at,
                "property_name": self._property_name,
                "unit_name": self._unit_name,
                "manager_name": self._manager_name,
            },
        }

    def _summary_html(
        self,
        *,
        generated_at: datetime,
        trigger: str,
        document_entries: list[HistoryDocumentEntry],
        written_documents: int,
        missing_files: list[dict[str, Any]],
    ) -> str:
        tenant_rows = "".join(
            (
                "<tr>"
                f"<td>{self._escape_html(str(tenant.pk))}</td>"
                f"<td>{self._escape_html(tenant.get_salutation_display())}</td>"
                f"<td>{self._escape_html((tenant.first_name or '').strip())}</td>"
                f"<td>{self._escape_html((tenant.last_name or '').strip())}</td>"
                f"<td>{self._escape_html(self._format_date(tenant.date_of_birth))}</td>"
                f"<td>{self._escape_html((tenant.email or '').strip() or '—')}</td>"
                f"<td>{self._escape_html((tenant.phone or '').strip() or '—')}</td>"
                f"<td>{self._escape_html((tenant.iban or '').strip() or '—')}</td>"
                "</tr>"
            )
            for tenant in self.lease.tenants.order_by("last_name", "first_name", "id")
        )
        if not tenant_rows:
            tenant_rows = "<tr><td colspan=\"8\">Keine Mieter zugeordnet.</td></tr>"

        document_rows = "".join(
            (
                "<tr>"
                f"<td>{entry.datei.pk}</td>"
                f"<td>{self._escape_html(entry.datei.original_name or os.path.basename(entry.datei.file.name or ''))}</td>"
                f"<td>{self._escape_html(entry.datei.get_kategorie_display())}</td>"
                f"<td>{'Ja' if entry.datei.is_archived else 'Nein'}</td>"
                f"<td>{self._escape_html(', '.join(entry.source_labels) or '—')}</td>"
                f"<td>{self._escape_html('documents/' + entry.archive_name)}</td>"
                "</tr>"
            )
            for entry in document_entries
        )
        if not document_rows:
            document_rows = "<tr><td colspan=\"6\">Keine Dokumente enthalten.</td></tr>"

        missing_rows = "".join(
            (
                "<tr>"
                f"<td>{row.get('datei_id', '—')}</td>"
                f"<td>{self._escape_html(str(row.get('original_name') or '—'))}</td>"
                f"<td>{self._escape_html(str(row.get('error') or '—'))}</td>"
                "</tr>"
            )
            for row in missing_files
        )
        if not missing_rows:
            missing_rows = "<tr><td colspan=\"3\">Keine fehlenden Dateien.</td></tr>"

        return f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Historie-Paket Mietvertrag #{self.lease.pk}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; color: #1f2937; }}
    h1 {{ margin-bottom: 0.25rem; }}
    .meta {{ color: #4b5563; margin-bottom: 1rem; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1rem; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 0.6rem; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 0.5rem; text-align: left; vertical-align: top; }}
    th {{ background: #f9fafb; }}
  </style>
</head>
<body>
  <h1>Historie-Paket Mietvertrag #{self.lease.pk}</h1>
  <div class="meta">Generiert am: {generated_at:%d.%m.%Y %H:%M:%S} · Trigger: {self._escape_html(trigger)}</div>

  <div class="card">
    <h2>Übersicht</h2>
    <table>
      <tbody>
        <tr><th>Liegenschaft</th><td>{self._escape_html(self._property_name)}</td></tr>
        <tr><th>Einheit</th><td>{self._escape_html(self._unit_name)}</td></tr>
        <tr><th>Verwalter</th><td>{self._escape_html(self._manager_name)}</td></tr>
        <tr><th>Status</th><td>{self._escape_html(self.lease.get_status_display())}</td></tr>
        <tr><th>Einzug</th><td>{self._escape_html(self._format_date(self.lease.entry_date))}</td></tr>
        <tr><th>Auszug</th><td>{self._escape_html(self._format_date(self.lease.exit_date))}</td></tr>
        <tr><th>Letzte Wertsicherung</th><td>{self._escape_html(self._format_date(self.lease.last_index_adjustment))}</td></tr>
        <tr><th>Index-Basiswert</th><td>{self._escape_html(self._format_decimal(self.lease.index_base_value))}</td></tr>
        <tr><th>HMZ Netto</th><td>{self._escape_html(self._format_money(self.lease.net_rent))}</td></tr>
        <tr><th>BK Netto</th><td>{self._escape_html(self._format_money(self.lease.operating_costs_net))}</td></tr>
        <tr><th>Heizung Netto</th><td>{self._escape_html(self._format_money(self.lease.heating_costs_net))}</td></tr>
        <tr><th>Kaution</th><td>{self._escape_html(self._format_money(self.lease.deposit))}</td></tr>
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2>Mieter</h2>
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Anrede</th>
          <th>Vorname</th>
          <th>Nachname</th>
          <th>Geburtsdatum</th>
          <th>E-Mail</th>
          <th>Telefon</th>
          <th>IBAN</th>
        </tr>
      </thead>
      <tbody>{tenant_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>Dokumente</h2>
    <p>Geschrieben: {written_documents} · Fehlend: {len(missing_files)}</p>
    <table>
      <thead>
        <tr>
          <th>Datei-ID</th>
          <th>Name</th>
          <th>Kategorie</th>
          <th>Archiviert</th>
          <th>Quelle</th>
          <th>ZIP-Pfad</th>
        </tr>
      </thead>
      <tbody>{document_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>Fehlende Dateien</h2>
    <table>
      <thead>
        <tr>
          <th>Datei-ID</th>
          <th>Name</th>
          <th>Fehler</th>
        </tr>
      </thead>
      <tbody>{missing_rows}</tbody>
    </table>
  </div>
</body>
</html>
"""

    @staticmethod
    def _is_history_package_file(datei: Datei) -> bool:
        return str(datei.beschreibung or "").startswith(LeaseHistoryPackageService.DESCRIPTION_PREFIX)

    @staticmethod
    def _safe_document_name(datei: Datei) -> str:
        original_name = str(datei.original_name or "").strip() or os.path.basename(str(datei.file.name or ""))
        stem = slugify(Path(original_name).stem) or f"datei-{datei.pk}"
        extension = Path(original_name).suffix.lower() or ".bin"
        return f"{datei.pk}_{stem}{extension}"

    @staticmethod
    def _read_file_bytes(datei: Datei) -> bytes:
        with datei.file.open("rb") as stream:
            return stream.read()

    @staticmethod
    def _format_date(value: date | datetime | None) -> str:
        if value is None:
            return "—"
        if isinstance(value, datetime):
            return timezone.localtime(value).strftime("%d.%m.%Y %H:%M")
        return value.strftime("%d.%m.%Y")

    @staticmethod
    def _format_decimal(value: Decimal | None) -> str:
        if value is None:
            return "—"
        return format(value, "f")

    @staticmethod
    def _format_money(value: Decimal | None) -> str:
        if value is None:
            return "—"
        quantized = Decimal(value).quantize(Decimal("0.01"))
        return f"{quantized} EUR"

    @staticmethod
    def _escape_html(value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    @classmethod
    def _json_ready(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, dict):
            return {key: cls._json_ready(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._json_ready(item) for item in value]
        return value
