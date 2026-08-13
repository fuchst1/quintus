from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from uuid import uuid4

from django.conf import settings
from django.utils import timezone


logger = logging.getLogger(__name__)


class BookkeepingPaperlessError(Exception):
    """User-facing Paperless error without response or credential details."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class BankStatementPaperlessMetadata:
    """Resolved Paperless metadata shared by upload and synchronization."""

    title: str
    created: str
    correspondent_id: int
    document_type_id: int
    storage_path_id: int
    tag_ids: tuple[int, ...]
    custom_field_ids: dict[str, int]
    custom_fields: dict[str, str]

    def multipart_fields(self) -> list[tuple[str, str]]:
        return [
            ("title", self.title),
            ("created", self.created),
            ("correspondent", str(self.correspondent_id)),
            ("document_type", str(self.document_type_id)),
            ("storage_path", str(self.storage_path_id)),
            *[("tags", str(tag_id)) for tag_id in self.tag_ids],
            ("custom_fields", json.dumps(self.custom_fields, ensure_ascii=False)),
        ]


class PaperlessClient:
    MAX_USER_ERROR_LENGTH = 500
    MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
    INVOICE_IMPORT_TAG_NAME = "Quintus-Import"
    INVOICE_IMPORTED_TAG_NAME = "Quintus-Importiert"
    INVOICE_ERROR_TAG_NAME = "Quintus-Fehler"
    BOOKKEEPING_REFERENCE_FIELD_NAME = "q_bookkeeping_referenz"
    CORRESPONDENT_NAME = "Erste Bank"
    DOCUMENT_TYPE_NAME = "Kontoauszug"
    TAG_NAMES = ("Buchhaltung", "Immo-Fuchs KG")
    STORAGE_PATH_NAME = "IFKG Kontoauszüge"
    MANUAL_CORRESPONDENT_NAME = "Diverse"
    MANUAL_DOCUMENT_TYPE_NAME = "Eingangsrechnung"
    MANUAL_STORAGE_PATH_NAME = "IFKG Eingangsrechnungen"
    SUPPORTING_CORRESPONDENT_NAME = "Diverse"
    SUPPORTING_DOCUMENT_TYPE_NAME = "Buchungsbeleg"
    SUPPORTING_MATCHING_STORAGE_PATH_NAME = "IFKG Matching-Nachweise"
    STORAGE_PATH_TEMPLATE = (
        "Immo-Fuchs KG/Buchhaltung/{{ created_year }}/Kontoauszuege/{{ title }}"
    )
    CUSTOM_FIELDS = {
        "q_bookkeeping_referenz": "string",
        "q_buchungsdatum": "date",
        "q_buchungsmonat": "string",
        "q_buchungsquartal": "string",
    }

    @classmethod
    def base_url(cls) -> str:
        raw_url = str(getattr(settings, "PAPERLESS_BASE_URL", "") or "").strip()
        raw_url = raw_url.rstrip("/")
        if raw_url.endswith("/api"):
            raw_url = raw_url[:-4]
        return raw_url

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.base_url() and cls._token())

    @classmethod
    def _token(cls) -> str:
        return str(getattr(settings, "PAPERLESS_API_TOKEN", "") or "").strip()

    @classmethod
    def _timeout(cls) -> int:
        try:
            timeout = int(getattr(settings, "PAPERLESS_TIMEOUT_SECONDS", 10))
        except (TypeError, ValueError):
            return 10
        return timeout if timeout > 0 else 10

    @classmethod
    def _api_url(cls, endpoint: str, query: dict[str, str] | None = None) -> str:
        url = f"{cls.base_url()}/api/{endpoint.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query)}"
        return url

    @classmethod
    def _request_json(
        cls,
        *,
        endpoint: str,
        method: str = "GET",
        query: dict[str, str] | None = None,
        payload: dict | None = None,
    ):
        if not cls.is_configured():
            raise BookkeepingPaperlessError(
                "Paperless ist nicht konfiguriert. Bitte die Paperless-Verbindung prüfen."
            )
        body = None
        headers = {
            "Authorization": f"Token {cls._token()}",
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            cls._api_url(endpoint, query),
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=cls._timeout()) as response:
                content = response.read()
        except HTTPError as exc:
            logger.warning("Paperless API HTTP %s for %s", exc.code, request.full_url)
            raise cls._http_error(exc) from None
        except (URLError, TimeoutError) as exc:
            logger.warning("Paperless API connection error for %s: %s", request.full_url, exc)
            raise cls._connection_error(exc) from None
        except Exception:
            logger.exception("Unexpected Paperless API error for %s", request.full_url)
            raise BookkeepingPaperlessError(
                "Die Anfrage an Paperless konnte nicht ausgeführt werden."
            ) from None
        if not content:
            return {}
        try:
            return json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise BookkeepingPaperlessError(
                "Paperless hat eine ungültige Antwort geliefert."
            ) from None

    @classmethod
    def _http_error(cls, error: HTTPError) -> BookkeepingPaperlessError:
        status_code = int(getattr(error, "code", 0) or 0)
        response_text = ""
        try:
            response_text = error.read().decode("utf-8", errors="replace")
        except Exception:
            logger.exception("Could not read Paperless HTTP error response")
        detail = cls._safe_error_text(response_text)
        if status_code in {401, 403}:
            message = "Paperless hat die Anmeldung oder Berechtigung abgelehnt."
        elif status_code in {400, 422}:
            message = detail or f"Paperless hat die Anfrage abgelehnt (HTTP {status_code})."
        elif status_code == 413:
            message = "Die Datei ist für Paperless zu groß."
        elif 500 <= status_code <= 599:
            message = f"Paperless ist derzeit nicht verfügbar (HTTP {status_code})."
        else:
            message = detail or f"Paperless antwortet mit HTTP-Status {status_code}."
        return BookkeepingPaperlessError(
            cls._safe_error_text(message),
            status_code=status_code,
        )

    @classmethod
    def _connection_error(cls, error: BaseException) -> BookkeepingPaperlessError:
        reason = getattr(error, "reason", error)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
            return BookkeepingPaperlessError(
                "Zeitüberschreitung bei der Verbindung zu Paperless."
            )
        return BookkeepingPaperlessError("Paperless ist nicht erreichbar.")

    @classmethod
    def _safe_error_text(cls, value) -> str:
        """Extract a short user-safe reason from arbitrary API error data."""
        value = cls._decode_json_value(value)
        if isinstance(value, dict):
            sensitive_keys = {
                "authorization",
                "api_token",
                "password",
                "secret",
                "token",
                "access_token",
            }
            for key in (
                "detail",
                "error_message",
                "message",
                "error",
                "result_data",
                "result",
            ):
                text = cls._safe_error_text(value.get(key))
                if text:
                    return text
            parts = [
                f"{key}: {cls._safe_error_text(item)}"
                for key, item in value.items()
                if str(key).lower() not in sensitive_keys
                if cls._safe_error_text(item)
            ]
            value = "; ".join(parts)
        elif isinstance(value, list):
            value = "; ".join(
                text for item in value if (text := cls._safe_error_text(item))
            )
        if value is None:
            return ""
        text = re.sub(r"\s+", " ", str(value)).strip()
        if not text:
            return ""
        text = re.sub(
            r"(?i)(authorization\s*:\s*|token\s+)[^\s,;]+",
            r"\1[redigiert]",
            text,
        )
        return text[: cls.MAX_USER_ERROR_LENGTH].rstrip()

    @classmethod
    def _find_exact_name(cls, endpoint: str, name: str) -> int | None:
        exact_ids = cls._find_exact_ids(endpoint, name)
        return exact_ids[0] if exact_ids else None

    @classmethod
    def _find_exact_ids(cls, endpoint: str, name: str) -> list[int]:
        payload = cls._request_json(
            endpoint=endpoint,
            query={"page_size": "200", "name": name},
        )
        if isinstance(payload, dict):
            results = payload.get("results", [])
        elif isinstance(payload, list):
            results = payload
        else:
            results = []
        exact_ids = []
        for item in results:
            if not isinstance(item, dict) or item.get("name") != name:
                continue
            try:
                item_id = int(item["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if item_id > 0 and item_id not in exact_ids:
                exact_ids.append(item_id)
        return exact_ids

    @classmethod
    def _require_named(cls, endpoint: str, name: str) -> int:
        existing_id = cls._find_exact_name(endpoint, name)
        if existing_id is not None:
            return existing_id
        raise BookkeepingPaperlessError(
            f"Das Paperless-Objekt '{name}' fehlt. "
            "Bitte zuerst exakt unter diesem Namen anlegen."
        )

    @classmethod
    def _require_custom_field(cls, name: str, data_type: str) -> int:
        existing_id = cls._find_exact_name("custom_fields/", name)
        if existing_id is not None:
            return existing_id
        raise BookkeepingPaperlessError(
            f"Das Paperless-Custom-Field '{name}' ({data_type}) fehlt. "
            "Bitte zuerst exakt unter diesem Namen anlegen."
        )

    @classmethod
    def _require_unique_tag(cls, name: str) -> int:
        exact_ids = cls._find_exact_ids("tags/", name)
        if len(exact_ids) == 1:
            return exact_ids[0]
        if len(exact_ids) > 1:
            raise BookkeepingPaperlessError(
                f"Der Paperless-Tag '{name}' existiert mehrfach. "
                "Bitte genau einen Tag mit diesem Namen verwenden."
            )
        raise BookkeepingPaperlessError(
            f"Der Paperless-Tag '{name}' fehlt. "
            "Bitte zuerst exakt unter diesem Namen anlegen."
        )

    @classmethod
    def _require_storage_path(cls, name: str | None = None) -> int:
        storage_path_name = name or cls.STORAGE_PATH_NAME
        exact_ids = cls._find_exact_ids("storage_paths/", storage_path_name)
        if len(exact_ids) == 1:
            return exact_ids[0]
        if len(exact_ids) > 1:
            raise BookkeepingPaperlessError(
                f"Der Paperless-Speicherpfad '{storage_path_name}' existiert mehrfach. "
                "Bitte genau einen Speicherpfad mit diesem Namen verwenden."
            )
        raise BookkeepingPaperlessError(
            f"Der Paperless-Speicherpfad '{storage_path_name}' fehlt. "
            "Bitte zuerst exakt unter diesem Namen anlegen."
        )

    @classmethod
    def build_bank_statement_metadata(cls, statement) -> BankStatementPaperlessMetadata:
        """Resolve the canonical metadata for a bank statement once."""
        if not cls.is_configured():
            raise BookkeepingPaperlessError(
                "Paperless ist nicht konfiguriert. Bitte die Paperless-Verbindung prüfen."
            )
        imported_tag_id = cls._require_unique_tag(cls.INVOICE_IMPORTED_TAG_NAME)
        correspondent_id = cls._require_named(
            "correspondents/", cls.CORRESPONDENT_NAME
        )
        document_type_id = cls._require_named(
            "document_types/", cls.DOCUMENT_TYPE_NAME
        )
        tag_ids = [
            cls._require_named("tags/", tag_name) for tag_name in cls.TAG_NAMES
        ]
        storage_path_id = cls._require_storage_path()
        custom_field_ids = {
            name: cls._require_custom_field(name, data_type)
            for name, data_type in cls.CUSTOM_FIELDS.items()
        }
        tag_ids = tuple(dict.fromkeys([*tag_ids, imported_tag_id]))
        custom_fields = {
            str(custom_field_ids["q_buchungsdatum"]): statement.statement_date.isoformat(),
            str(custom_field_ids["q_buchungsmonat"]): statement.booking_month,
            str(custom_field_ids["q_buchungsquartal"]): statement.booking_quarter,
            str(custom_field_ids["q_bookkeeping_referenz"]): str(statement.reference_uuid),
        }
        return BankStatementPaperlessMetadata(
            title=f"Kontoauszug {statement.booking_month} – {statement.iban}",
            created=statement.statement_date.isoformat(),
            correspondent_id=correspondent_id,
            document_type_id=document_type_id,
            storage_path_id=storage_path_id,
            tag_ids=tag_ids,
            custom_field_ids=custom_field_ids,
            custom_fields=custom_fields,
        )

    @classmethod
    def upload_bank_statement(cls, statement) -> str:
        metadata = cls.build_bank_statement_metadata(statement)
        try:
            with statement.temporary_pdf.open("rb") as pdf_file:
                response = cls._request_multipart(
                    form_fields=metadata.multipart_fields(),
                    file_name=os.path.basename(statement.temporary_pdf.name),
                    file_content=pdf_file.read(),
                )
        except OSError:
            raise BookkeepingPaperlessError(
                "Die temporäre PDF-Datei konnte nicht gelesen werden."
            ) from None
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            for key in ("task_id", "task", "uuid", "id"):
                if response.get(key):
                    return str(response[key])
        raise BookkeepingPaperlessError(
            "Paperless hat keine Task-ID für den Upload zurückgegeben."
        )

    @classmethod
    def upload_manual_invoice(cls, invoice) -> str:
        if not cls.is_configured():
            raise BookkeepingPaperlessError(
                "Paperless ist nicht konfiguriert. Bitte die Paperless-Verbindung prüfen."
            )
        imported_tag_id = cls._require_unique_tag(cls.INVOICE_IMPORTED_TAG_NAME)
        correspondent_id = cls._require_named(
            "correspondents/", cls.MANUAL_CORRESPONDENT_NAME
        )
        document_type_id = cls._require_named(
            "document_types/", cls.MANUAL_DOCUMENT_TYPE_NAME
        )
        tag_ids = [
            cls._require_named("tags/", tag_name) for tag_name in cls.TAG_NAMES
        ]
        storage_path_id = cls._require_storage_path(cls.MANUAL_STORAGE_PATH_NAME)
        reference_field_id = cls._require_custom_field(
            "q_bookkeeping_referenz",
            cls.CUSTOM_FIELDS["q_bookkeeping_referenz"],
        )
        title = (
            f"Eingangsrechnung {invoice.invoice_number or 'ohne Rechnungsnummer'}"
            f" – {invoice.partner_name or 'Diverse'}"
        )
        form_fields = [
            ("title", title),
            ("created", (invoice.invoice_date or timezone.localdate()).isoformat()),
            ("correspondent", str(correspondent_id)),
            ("document_type", str(document_type_id)),
            ("storage_path", str(storage_path_id)),
            *[("tags", str(tag_id)) for tag_id in tag_ids],
            ("tags", str(imported_tag_id)),
            (
                "custom_fields",
                json.dumps(
                    {
                        str(reference_field_id): str(invoice.reference_uuid),
                    },
                    ensure_ascii=False,
                ),
            ),
        ]
        try:
            with invoice.temporary_pdf.open("rb") as pdf_file:
                response = cls._request_multipart(
                    form_fields=form_fields,
                    file_name=os.path.basename(invoice.temporary_pdf.name),
                    file_content=pdf_file.read(),
                )
        except OSError:
            raise BookkeepingPaperlessError(
                "Die temporäre Rechnungs-PDF konnte nicht gelesen werden."
            ) from None
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            for key in ("task_id", "task", "uuid", "id"):
                if response.get(key):
                    return str(response[key])
        raise BookkeepingPaperlessError(
            "Paperless hat keine Task-ID für den Rechnungsupload zurückgegeben."
        )

    @classmethod
    def upload_supporting_document(cls, document) -> str:
        """Upload a matching-rule or bank-transaction supporting PDF."""
        if not cls.is_configured():
            raise BookkeepingPaperlessError(
                "Paperless ist nicht konfiguriert. Bitte die Paperless-Verbindung prüfen."
            )
        imported_tag_id = cls._require_unique_tag(cls.INVOICE_IMPORTED_TAG_NAME)
        correspondent_id = cls._require_named(
            "correspondents/", cls.SUPPORTING_CORRESPONDENT_NAME
        )
        document_type_id = cls._require_named(
            "document_types/", cls.SUPPORTING_DOCUMENT_TYPE_NAME
        )
        tag_ids = [
            cls._require_named("tags/", tag_name) for tag_name in cls.TAG_NAMES
        ]
        storage_path_name = (
            cls.SUPPORTING_MATCHING_STORAGE_PATH_NAME
            if document.matching_rule_id
            else cls.MANUAL_STORAGE_PATH_NAME
        )
        storage_path_id = cls._require_storage_path(storage_path_name)
        reference_field_id = cls._require_custom_field(
            "q_bookkeeping_referenz",
            cls.CUSTOM_FIELDS["q_bookkeeping_referenz"],
        )

        if document.matching_rule_id:
            title = (
                f"Matching-Nachweis {document.matching_rule.name} "
                f"– Version {document.matching_rule.version_number}"
            )
            created = document.created_at.date().isoformat()
            custom_field_values = {str(reference_field_id): str(document.reference_uuid)}
        else:
            bank_transaction = document.bank_transaction
            document_date = bank_transaction.value_date or bank_transaction.booking_date
            name = bank_transaction.partner_name or "–"
            amount = format(bank_transaction.amount, "f")
            title = f"Buchungsbeleg {document_date.isoformat()} – {name} – {amount}"
            booking_month = document_date.strftime("%Y-%m")
            booking_quarter = (
                f"{document_date.year}-Q{((document_date.month - 1) // 3) + 1}"
            )
            custom_field_values = {
                str(reference_field_id): str(document.reference_uuid),
            }
            for field_name, value in {
                "q_buchungsdatum": document_date.isoformat(),
                "q_buchungsmonat": booking_month,
                "q_buchungsquartal": booking_quarter,
            }.items():
                field_id = cls._require_custom_field(
                    field_name,
                    cls.CUSTOM_FIELDS[field_name],
                )
                custom_field_values[str(field_id)] = value
            created = document_date.isoformat()

        form_fields = [
            ("title", title),
            ("created", created),
            ("correspondent", str(correspondent_id)),
            ("document_type", str(document_type_id)),
            ("storage_path", str(storage_path_id)),
            *[("tags", str(tag_id)) for tag_id in tag_ids],
            ("tags", str(imported_tag_id)),
            (
                "custom_fields",
                json.dumps(custom_field_values, ensure_ascii=False),
            ),
        ]
        try:
            with document.temporary_file.open("rb") as pdf_file:
                response = cls._request_multipart(
                    form_fields=form_fields,
                    file_name=os.path.basename(document.original_filename),
                    file_content=pdf_file.read(),
                )
        except OSError:
            raise BookkeepingPaperlessError(
                "Die temporäre PDF-Datei konnte nicht gelesen werden."
            ) from None
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            for key in ("task_id", "task", "uuid", "id"):
                if response.get(key):
                    return str(response[key])
        raise BookkeepingPaperlessError(
            "Paperless hat keine Task-ID für den Belegupload zurückgegeben."
        )

    @classmethod
    def update_manual_invoice_dates(cls, invoice) -> None:
        """Update only the confirmed booking-date fields of an existing document."""
        document_id = int(invoice.paperless_document_id or 0)
        if document_id <= 0:
            raise BookkeepingPaperlessError(
                "Für die Paperless-Datumsfelder fehlt die Dokument-ID."
            )
        if invoice.payment_date is None:
            raise BookkeepingPaperlessError(
                "Für die Paperless-Datumsfelder fehlt das Zahlungsdatum."
            )
        document = cls._request_json(endpoint=f"documents/{document_id}/")
        if not isinstance(document, dict):
            raise BookkeepingPaperlessError(
                "Paperless hat keine verwertbaren Dokumentdaten zurückgegeben."
            )
        custom_fields = document.get("custom_fields")
        values = {
            "q_buchungsdatum": invoice.payment_date.isoformat(),
            "q_buchungsmonat": invoice.payment_date.strftime("%Y-%m"),
            "q_buchungsquartal": (
                f"{invoice.payment_date.year}-Q"
                f"{((invoice.payment_date.month - 1) // 3) + 1}"
            ),
        }
        updated_custom_fields = custom_fields
        for field_name, value in values.items():
            field_id = cls._require_custom_field(
                field_name,
                cls.CUSTOM_FIELDS[field_name],
            )
            updated_custom_fields = cls._replace_custom_field_value(
                updated_custom_fields,
                field_id=field_id,
                field_name=field_name,
                value=value,
                append_if_missing=True,
            )
        cls._request_json(
            endpoint=f"documents/{document_id}/",
            method="PATCH",
            payload={"custom_fields": updated_custom_fields},
        )

    @classmethod
    def task_status(cls, task_id: str) -> dict[str, object]:
        payload = cls._request_json(
            endpoint="tasks/",
            query={"task_id": str(task_id), "page_size": "200"},
        )
        task = cls._extract_task_payload(payload, task_id=str(task_id))
        if task is None:
            return {
                "status": "needs_fallback",
                "document_id": None,
                "message": "Der Paperless-Task wurde nicht gefunden.",
                "found": False,
            }
        raw_status = cls._normalize_task_status(task)
        message = cls._task_error_message(task)
        duplicate_id, duplicate_in_trash = cls._duplicate_info(task, message)
        if duplicate_id is not None:
            return {
                "status": "duplicate",
                "document_id": duplicate_id,
                "duplicate_in_trash": duplicate_in_trash,
                "document_verified": False,
                "message": "",
                "found": True,
            }
        if raw_status in {"failure", "failed"}:
            return {
                "status": "failed",
                "document_id": None,
                "message": message,
                "found": True,
            }
        if raw_status in {"pending", "started", "retry", "running"}:
            return {
                "status": "pending",
                "document_id": None,
                "message": "",
                "found": True,
            }
        document_id = cls._document_id(task)
        if document_id is not None:
            return {
                "status": "completed",
                "document_id": document_id,
                "document_verified": False,
                "message": "",
                "found": True,
            }
        if raw_status in {"success", "completed"}:
            message = "Der erfolgreiche Paperless-Task enthält keine Dokument-ID."
        else:
            message = "Die Paperless-Task-Antwort enthält keine verwertbare Dokument-ID."
        return {
            "status": "needs_fallback",
            "document_id": None,
            "message": message,
            "found": True,
        }

    @classmethod
    def verify_document_id(cls, document_id: int) -> dict:
        """Verify that the configured Paperless account can read the document."""
        try:
            return cls.document_details(document_id)
        except BookkeepingPaperlessError:
            raise
        except Exception:
            logger.exception("Unexpected error while verifying Paperless document %s", document_id)
            raise BookkeepingPaperlessError(
                "Das Paperless-Dokument konnte nicht verifiziert werden."
            ) from None

    @classmethod
    def synchronize_bank_statement_metadata(
        cls,
        statement,
        document_id: int | None = None,
        *,
        document: dict | None = None,
    ) -> dict[str, object]:
        """Merge canonical bank-statement metadata into an existing document."""
        normalized_id = cls._coerce_document_id(
            document_id if document_id is not None else getattr(statement, "paperless_document_id", None)
        )
        if normalized_id is None:
            raise BookkeepingPaperlessError(
                "Für die Paperless-Metadaten fehlt die Dokument-ID."
            )
        if not isinstance(document, dict):
            document = cls.document_details(normalized_id)
        metadata = cls.build_bank_statement_metadata(statement)

        current_tags = cls._document_tag_ids(document.get("tags", []))
        merged_tags = current_tags + [
            tag_id for tag_id in metadata.tag_ids if tag_id not in current_tags
        ]
        merged_custom_fields = document.get("custom_fields")
        reference_name = "q_bookkeeping_referenz"
        reference_id = metadata.custom_field_ids[reference_name]
        found_reference, current_reference = cls._read_custom_field_value(
            merged_custom_fields,
            field_id=reference_id,
            field_name=reference_name,
        )
        expected_reference = metadata.custom_fields[str(reference_id)]
        if found_reference and current_reference and current_reference != expected_reference:
            raise BookkeepingPaperlessError(
                "Das Paperless-Dokument ist bereits mit einem anderen "
                "Bookkeeping-Datensatz verknüpft."
            )
        for field_name, field_id in metadata.custom_field_ids.items():
            merged_custom_fields = cls._replace_custom_field_value(
                merged_custom_fields,
                field_id=field_id,
                field_name=field_name,
                value=metadata.custom_fields[str(field_id)],
                append_if_missing=True,
            )

        payload = {
            "title": metadata.title,
            "created": metadata.created,
            "correspondent": metadata.correspondent_id,
            "document_type": metadata.document_type_id,
            "storage_path": metadata.storage_path_id,
            "tags": merged_tags,
            "custom_fields": merged_custom_fields,
        }
        cls._request_json(
            endpoint=f"documents/{normalized_id}/",
            method="PATCH",
            payload=payload,
        )
        return {
            "status": "synced",
            "document_id": normalized_id,
            "metadata": metadata,
            "document": document,
        }

    @classmethod
    def _duplicate_document_id(cls, task: dict, message: str) -> int | None:
        """Extract a document ID only when the task clearly reports a duplicate."""
        document_id, _duplicate_in_trash = cls._duplicate_info(task, message)
        return document_id

    @classmethod
    def _duplicate_info(
        cls,
        task: dict,
        message: str = "",
    ) -> tuple[int | None, bool]:
        """Return the Paperless duplicate ID and whether it is in the trash.

        Paperless has returned both structured task fields and serialized text
        over time.  Only an explicit ``duplicate_of`` marker or a known
        duplicate message is accepted; arbitrary numbers in an error are not.
        """
        sources = [
            task.get("result_data"),
            task.get("result"),
            task.get("detail"),
            task.get("error"),
            task.get("message"),
            task,
        ]
        for source in sources:
            duplicate = cls._find_structured_duplicate(cls._decode_json_value(source))
            if duplicate is not None:
                return duplicate

        text_sources = [message]
        text_sources.extend(
            text
            for source in sources
            if (text := cls._safe_error_text(source))
            and text not in text_sources
        )
        duplicate_of_pattern = re.compile(
            r"\bduplicate_of\s*[:=]\s*[\"']?(\d+)",
            re.IGNORECASE,
        )
        trash_pattern = re.compile(
            r"\bduplicate_in_trash\s*[:=]\s*[\"']?(true|false)\b",
            re.IGNORECASE,
        )
        for text in text_sources:
            match = duplicate_of_pattern.search(text)
            if match is not None:
                document_id = cls._coerce_document_id(match.group(1))
                if document_id is not None:
                    trash_match = trash_pattern.search(text)
                    return document_id, bool(
                        trash_match and trash_match.group(1).lower() == "true"
                    )

        duplicate_messages = [
            text
            for text in text_sources
            if re.search(r"\b(?:duplicate|duplikat)\b", text, re.IGNORECASE)
        ]
        if not duplicate_messages:
            return None, False
        for candidate in (
            task.get("related_document"),
            task.get("related_document_id"),
            task.get("result_data"),
            cls._decode_json_value(task.get("result")),
        ):
            document_id = cls._coerce_document_id(candidate)
            if document_id is not None:
                return document_id, False
        for duplicate_message in duplicate_messages:
            match = re.search(
                r"\b(?:duplicate|duplikat)\b.{0,120}\b"
                r"(?:of|von|document|dokument|test)\b.{0,80}?#\s*(\d+)",
                duplicate_message,
                re.IGNORECASE,
            )
            if match is not None:
                document_id = cls._coerce_document_id(match.group(1))
                if document_id is not None:
                    return document_id, False
        return None, False

    @classmethod
    def _find_structured_duplicate(cls, value) -> tuple[int, bool] | None:
        value = cls._decode_json_value(value)
        if isinstance(value, dict):
            if "duplicate_of" in value:
                document_id = cls._coerce_document_id(value.get("duplicate_of"))
                if document_id is not None:
                    return document_id, cls._coerce_bool(
                        value.get("duplicate_in_trash"),
                    )
            for nested in value.values():
                duplicate = cls._find_structured_duplicate(nested)
                if duplicate is not None:
                    return duplicate
        elif isinstance(value, list):
            for nested in value:
                duplicate = cls._find_structured_duplicate(nested)
                if duplicate is not None:
                    return duplicate
        return None

    @staticmethod
    def _coerce_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() == "true"
        return False

    @classmethod
    def find_document_by_reference(cls, reference: str) -> dict[str, object]:
        normalized_reference = str(reference or "").strip()
        if not normalized_reference:
            raise BookkeepingPaperlessError(
                "Für die Paperless-Suche fehlt die Bookkeeping-Referenz."
            )
        custom_field_query = json.dumps(
            ["q_bookkeeping_referenz", "exact", normalized_reference],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        payload = cls._request_json(
            endpoint="documents/",
            query={
                "custom_field_query": custom_field_query,
                "page_size": "200",
            },
        )
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            documents = payload["results"]
            count = payload.get("count")
            try:
                if count is not None and int(count) > 1:
                    raise BookkeepingPaperlessError(
                        "In Paperless wurden mehrere Dokumente mit derselben "
                        "Bookkeeping-Referenz gefunden."
                    )
            except (TypeError, ValueError):
                pass
        elif isinstance(payload, list):
            documents = payload
        elif isinstance(payload, dict):
            documents = [payload]
        else:
            documents = []

        if len(documents) == 0:
            return {
                "status": "pending",
                "document_id": None,
                "document_verified": False,
                "message": "",
            }
        if len(documents) > 1:
            raise BookkeepingPaperlessError(
                "In Paperless wurden mehrere Dokumente mit derselben "
                "Bookkeeping-Referenz gefunden."
            )
        document = documents[0]
        document_id = (
            cls._coerce_document_id(document.get("id"))
            if isinstance(document, dict)
            else None
        )
        if document_id is None:
            raise BookkeepingPaperlessError(
                "Das Paperless-Dokument zur Bookkeeping-Referenz enthält keine "
                "verwertbare Dokument-ID."
            )
        return {
            "status": "completed",
            "document_id": document_id,
            "document_verified": False,
            "message": "",
        }

    @classmethod
    def paperless_invoice_import_master_data(cls) -> dict[str, object]:
        """Resolve import tags and the reference field by their exact names."""
        import_tag_ids = cls._find_exact_ids(
            "tags/",
            cls.INVOICE_IMPORT_TAG_NAME,
        )
        if not import_tag_ids:
            raise BookkeepingPaperlessError(
                f"Das Paperless-Objekt '{cls.INVOICE_IMPORT_TAG_NAME}' fehlt. "
                "Bitte zuerst exakt unter diesem Namen anlegen."
            )
        return {
            "import_tag_id": import_tag_ids[0],
            "import_tag_ids": tuple(import_tag_ids),
            "imported_tag_id": cls._require_named(
                "tags/",
                cls.INVOICE_IMPORTED_TAG_NAME,
            ),
            "error_tag_id": cls._require_named(
                "tags/",
                cls.INVOICE_ERROR_TAG_NAME,
            ),
            "reference_field_id": cls._require_custom_field(
                cls.BOOKKEEPING_REFERENCE_FIELD_NAME,
                "string",
            ),
        }

    @classmethod
    def documents_by_tag_id(
        cls,
        tag_id: int | list[int] | tuple[int, ...],
    ) -> list[dict]:
        """Return all documents matching one exact Paperless tag ID."""
        raw_tag_ids = tag_id if isinstance(tag_id, (list, tuple)) else (tag_id,)
        normalized_tag_ids = []
        for raw_tag_id in raw_tag_ids:
            try:
                normalized_tag_id = int(raw_tag_id)
            except (TypeError, ValueError):
                normalized_tag_id = 0
            if normalized_tag_id > 0 and normalized_tag_id not in normalized_tag_ids:
                normalized_tag_ids.append(normalized_tag_id)
        if not normalized_tag_ids:
            raise BookkeepingPaperlessError(
                "Für die Paperless-Dokumentabfrage fehlt eine gültige Tag-ID."
            )

        documents = []
        page_size = 100
        seen_document_ids = set()
        for normalized_tag_id in normalized_tag_ids:
            page = 1
            tag_result_count = 0
            while True:
                payload = cls._request_json(
                    endpoint="documents/",
                    query={
                        "tags__id": str(normalized_tag_id),
                        "page": str(page),
                        "page_size": str(page_size),
                    },
                )
                if isinstance(payload, dict):
                    page_results = payload.get("results", [])
                    total_count = payload.get("count")
                    next_page = payload.get("next")
                elif isinstance(payload, list):
                    page_results = payload
                    total_count = None
                    next_page = None
                else:
                    page_results = []
                    total_count = 0
                    next_page = None
                if not isinstance(page_results, list):
                    raise BookkeepingPaperlessError(
                        "Paperless hat eine ungültige Dokumentliste geliefert."
                    )
                tag_result_count += len(page_results)
                for item in page_results:
                    if not isinstance(item, dict):
                        continue
                    document_id = cls._coerce_document_id(item.get("id"))
                    if document_id is not None:
                        if document_id in seen_document_ids:
                            continue
                        seen_document_ids.add(document_id)
                    documents.append(item)
                if not next_page:
                    try:
                        complete = total_count is not None and tag_result_count >= int(
                            total_count
                        )
                    except (TypeError, ValueError):
                        complete = len(page_results) < page_size
                    if complete or len(page_results) < page_size:
                        break
                page += 1
                if page > 10000:
                    raise BookkeepingPaperlessError(
                        "Paperless liefert eine unerwartet lange Dokumentpagination."
                    )
        return documents

    @classmethod
    def document_details(cls, document_id: int) -> dict:
        normalized_id = cls._coerce_document_id(document_id)
        if normalized_id is None:
            raise BookkeepingPaperlessError(
                "Für die Paperless-Dokumentdetails fehlt die Dokument-ID."
            )
        payload = cls._request_json(endpoint=f"documents/{normalized_id}/")
        if not isinstance(payload, dict):
            raise BookkeepingPaperlessError(
                "Paperless hat keine verwertbaren Dokumentdetails zurückgegeben."
            )
        return payload

    @classmethod
    def update_invoice_import_markers(
        cls,
        document_id: int,
        *,
        reference_uuid: str,
        import_tag_id: int,
        imported_tag_id: int,
        error_tag_id: int,
        reference_field_id: int,
        import_tag_ids: tuple[int, ...] | list[int] | None = None,
    ) -> None:
        """Preserve document metadata while updating only process markers."""
        document = cls.document_details(document_id)
        tags = cls._document_tag_ids(document.get("tags"))
        custom_fields = cls._replace_custom_field_value(
            document.get("custom_fields"),
            field_id=int(reference_field_id),
            field_name=cls.BOOKKEEPING_REFERENCE_FIELD_NAME,
            value=str(reference_uuid),
            append_if_missing=True,
        )
        updated_tags = cls._merge_process_tags(
            tags,
            remove_ids={
                int(import_tag_id),
                int(error_tag_id),
                *(
                    int(tag_id)
                    for tag_id in (import_tag_ids or ())
                ),
            },
            add_id=int(imported_tag_id),
        )
        if (
            updated_tags == tags
            and custom_fields == document.get("custom_fields")
        ):
            return
        cls._request_json(
            endpoint=f"documents/{int(document_id)}/",
            method="PATCH",
            payload={
                "tags": updated_tags,
                "custom_fields": custom_fields,
            },
        )

    @classmethod
    def update_invoice_import_error_tag(
        cls,
        document_id: int,
        *,
        import_tag_id: int,
        imported_tag_id: int,
        error_tag_id: int,
        import_tag_ids: tuple[int, ...] | list[int] | None = None,
    ) -> None:
        """Mark a document as failed without changing its other tags."""
        document = cls.document_details(document_id)
        tags = cls._document_tag_ids(document.get("tags"))
        updated_tags = cls._merge_process_tags(
            tags,
            remove_ids={
                int(import_tag_id),
                int(imported_tag_id),
                *(
                    int(tag_id)
                    for tag_id in (import_tag_ids or ())
                ),
            },
            add_id=int(error_tag_id),
        )
        if updated_tags == tags:
            return
        cls._request_json(
            endpoint=f"documents/{int(document_id)}/",
            method="PATCH",
            payload={"tags": updated_tags},
        )

    @staticmethod
    def _document_tag_ids(raw_tags) -> list[int]:
        if not isinstance(raw_tags, list):
            raise BookkeepingPaperlessError(
                "Das Paperless-Dokument enthält keine verwertbare Tag-Liste."
            )
        tag_ids = []
        for tag in raw_tags:
            candidate = tag.get("id") if isinstance(tag, dict) else tag
            try:
                normalized = int(candidate)
            except (TypeError, ValueError):
                raise BookkeepingPaperlessError(
                    "Das Paperless-Dokument enthält eine ungültige Tag-ID."
                ) from None
            if normalized > 0 and normalized not in tag_ids:
                tag_ids.append(normalized)
        return tag_ids

    @staticmethod
    def _merge_process_tags(
        current_tag_ids: list[int],
        *,
        remove_ids: set[int],
        add_id: int,
    ) -> list[int]:
        result = [
            tag_id
            for tag_id in current_tag_ids
            if tag_id not in remove_ids and tag_id != add_id
        ]
        result.append(add_id)
        return result

    @classmethod
    def synchronize_statement_reference(cls, statement) -> dict[str, object]:
        document_id = int(statement.paperless_document_id or 0)
        if document_id <= 0:
            raise BookkeepingPaperlessError(
                "Für den BankStatement-Datensatz fehlt die Paperless-Dokument-ID."
            )
        document = cls._request_json(endpoint=f"documents/{document_id}/")
        if not isinstance(document, dict):
            raise BookkeepingPaperlessError(
                "Paperless hat keine verwertbaren Dokumentdaten zurückgegeben."
            )

        field_name = "q_bookkeeping_referenz"
        field_id = cls._find_exact_name("custom_fields/", field_name)
        if field_id is None:
            raise BookkeepingPaperlessError(
                f"Das Paperless-Custom-Field '{field_name}' fehlt."
            )

        custom_fields = document.get("custom_fields")
        found, current_reference = cls._read_custom_field_value(
            custom_fields,
            field_id=field_id,
            field_name=field_name,
        )
        if not found:
            raise BookkeepingPaperlessError(
                f"Das Paperless-Dokument enthält kein '{field_name}'-Feld."
            )

        new_reference = str(statement.reference_uuid)
        old_reference = str(statement.pk)
        if current_reference == new_reference:
            return {"status": "synced", "document_id": document_id}
        if current_reference != old_reference:
            raise BookkeepingPaperlessError(
                "Die bestehende Paperless-Referenz stimmt weder mit der alten "
                "noch mit der neuen Bookkeeping-Referenz überein."
            )

        updated_custom_fields = cls._replace_custom_field_value(
            custom_fields,
            field_id=field_id,
            field_name=field_name,
            value=new_reference,
        )
        cls._request_json(
            endpoint=f"documents/{document_id}/",
            method="PATCH",
            payload={"custom_fields": updated_custom_fields},
        )
        return {"status": "synced", "document_id": document_id}

    @classmethod
    def _read_custom_field_value(
        cls,
        custom_fields,
        *,
        field_id: int,
        field_name: str,
    ) -> tuple[bool, str]:
        if isinstance(custom_fields, dict):
            for key, value in custom_fields.items():
                if str(key) in {str(field_id), field_name}:
                    return True, str(value or "").strip()
            return False, ""
        if isinstance(custom_fields, list):
            for entry in custom_fields:
                if not isinstance(entry, dict):
                    continue
                field = entry.get("field") or entry.get("field_id")
                if isinstance(field, dict):
                    field_id_value = field.get("id")
                    field_name_value = field.get("name")
                else:
                    field_id_value = field
                    field_name_value = entry.get("field_name") or (
                        field if isinstance(field, str) else None
                    )
                if str(field_id_value) == str(field_id) or field_name_value == field_name:
                    return True, str(entry.get("value") or "").strip()
        return False, ""

    @classmethod
    def _replace_custom_field_value(
        cls,
        custom_fields,
        *,
        field_id: int,
        field_name: str,
        value: str,
        append_if_missing: bool = False,
    ):
        if isinstance(custom_fields, dict):
            updated = dict(custom_fields)
            for key in list(updated):
                if str(key) == str(field_id) or str(key) == field_name:
                    updated[key] = value
                    return updated
            if append_if_missing:
                updated[str(field_id)] = value
                return updated
        elif isinstance(custom_fields, list):
            updated = []
            replaced = False
            for entry in custom_fields:
                if not isinstance(entry, dict):
                    updated.append(entry)
                    continue
                copied_entry = dict(entry)
                field = copied_entry.get("field") or copied_entry.get("field_id")
                field_id_value = field.get("id") if isinstance(field, dict) else field
                field_name_value = (
                    field.get("name")
                    if isinstance(field, dict)
                    else copied_entry.get("field_name") or (
                        field if isinstance(field, str) else None
                    )
                )
                if (
                    str(field_id_value) == str(field_id)
                    or field_name_value == field_name
                ):
                    copied_entry["value"] = value
                    replaced = True
                updated.append(copied_entry)
            if replaced:
                return updated
            if append_if_missing:
                updated.append({"field": field_id, "value": value})
                return updated
        if custom_fields is None and append_if_missing:
            return [{"field": field_id, "value": value}]
        raise BookkeepingPaperlessError(
            f"Das Paperless-Dokument enthält kein '{field_name}'-Feld und konnte nicht ergänzt werden."
        )

    @classmethod
    def _extract_task_payload(
        cls,
        payload,
        *,
        task_id: str,
    ) -> dict | None:
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            candidates = [item for item in payload["results"] if isinstance(item, dict)]
        elif isinstance(payload, list):
            candidates = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            candidates = [payload]
        else:
            candidates = []

        normalized_task_id = str(task_id).strip()
        for candidate in candidates:
            if cls._task_identifier(candidate) == normalized_task_id:
                return candidate
        if len(candidates) == 1 and not cls._task_identifier(candidates[0]):
            return candidates[0]
        return None

    @staticmethod
    def _task_identifier(task: dict) -> str:
        for key in ("task_id", "id", "uuid", "task"):
            value = task.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    @staticmethod
    def _decode_json_value(value):
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized or normalized[0] not in "[{":
            return value
        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            return value

    @classmethod
    def _normalize_task_status(cls, task: dict) -> str:
        raw_status = task.get("status")
        if raw_status not in (None, ""):
            return str(raw_status).strip().lower()
        result = cls._decode_json_value(task.get("result"))
        if isinstance(result, dict) and result.get("status") not in (None, ""):
            return str(result["status"]).strip().lower()
        if isinstance(result, str):
            normalized_result = result.strip().lower()
            if normalized_result in {
                "pending",
                "started",
                "retry",
                "running",
                "success",
                "completed",
                "failure",
                "failed",
            }:
                return normalized_result
        return ""

    @classmethod
    def _task_error_message(cls, task: dict) -> str:
        candidates = [
            task.get("message"),
            task.get("error"),
            task.get("detail"),
            task.get("result_data"),
        ]
        result = cls._decode_json_value(task.get("result"))
        for candidate in candidates:
            message = cls._safe_error_text(candidate)
            if message:
                return message
        if isinstance(result, dict):
            message = cls._safe_error_text(result)
            if message:
                return message
        elif result not in (None, ""):
            message = cls._safe_error_text(result)
            if message:
                return message
        return "Paperless meldet einen Fehler beim Upload."

    @classmethod
    def document_url(cls, document_id: int | None) -> str:
        if document_id is None or not cls.base_url():
            return ""
        return urljoin(f"{cls.base_url()}/", f"documents/{int(document_id)}/")

    @classmethod
    def delete_document(cls, document_id: int | None) -> None:
        try:
            normalized_id = int(document_id or 0)
        except (TypeError, ValueError):
            normalized_id = 0
        if normalized_id <= 0:
            raise BookkeepingPaperlessError(
                "Für die Paperless-Löschung fehlt die Dokument-ID."
            )
        cls._request_json(
            endpoint=f"documents/{normalized_id}/",
            method="DELETE",
        )

    @classmethod
    def document_ocr_text(cls, document_id: int | None) -> str:
        if document_id is None:
            raise BookkeepingPaperlessError(
                "Für die OCR-Abfrage fehlt die Paperless-Dokument-ID."
            )
        payload = cls._request_json(endpoint=f"documents/{int(document_id)}/")
        if not isinstance(payload, dict):
            raise BookkeepingPaperlessError(
                "Paperless hat keine verwertbaren Dokumentdaten zurückgegeben."
            )
        content = payload.get("content")
        if not isinstance(content, str):
            return ""
        return content.strip()

    @classmethod
    def download_document(cls, document_id: int | None) -> bytes:
        """Download the original binary document from Paperless."""
        normalized_id = cls._coerce_document_id(document_id)
        if normalized_id is None:
            raise BookkeepingPaperlessError(
                "Für den Paperless-Download fehlt eine gültige Dokument-ID."
            )
        if not cls.is_configured():
            raise BookkeepingPaperlessError(
                "Paperless ist nicht konfiguriert. Bitte die Paperless-Verbindung prüfen."
            )

        request = Request(
            cls._api_url(f"documents/{normalized_id}/download/"),
            headers={
                "Authorization": f"Token {cls._token()}",
                "Accept": "application/pdf, application/octet-stream, */*",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=cls._timeout()) as response:
                content_type = cls._response_content_type(response)
                if not cls._is_binary_content_type(content_type):
                    raise BookkeepingPaperlessError(
                        "Paperless hat statt einer Binärdatei eine unerwartete "
                        "Antwort geliefert."
                    )
                content_length = cls._response_content_length(response)
                if content_length is not None and content_length > cls.MAX_DOWNLOAD_BYTES:
                    raise BookkeepingPaperlessError(
                        "Das Paperless-Dokument ist für den Übergabepaket-Download zu groß."
                    )
                content = bytearray()
                while True:
                    chunk = response.read(min(1024 * 1024, cls.MAX_DOWNLOAD_BYTES + 1))
                    if not chunk:
                        break
                    content.extend(chunk)
                    if len(content) > cls.MAX_DOWNLOAD_BYTES:
                        raise BookkeepingPaperlessError(
                            "Das Paperless-Dokument ist für den Übergabepaket-Download zu groß."
                        )
                return bytes(content)
        except HTTPError as exc:
            if exc.code == 404:
                raise BookkeepingPaperlessError(
                    "Das Paperless-Dokument wurde nicht gefunden.",
                    status_code=404,
                ) from None
            if exc.code in {401, 403}:
                raise BookkeepingPaperlessError(
                    "Paperless hat den Zugriff abgelehnt. Bitte den API-Token prüfen.",
                    status_code=exc.code,
                ) from None
            raise BookkeepingPaperlessError(
                f"Paperless antwortet mit HTTP-Status {exc.code}.",
                status_code=exc.code,
            ) from None
        except (URLError, TimeoutError):
            raise BookkeepingPaperlessError(
                "Paperless ist nicht erreichbar oder die Anfrage hat zu lange gedauert."
            ) from None
        except BookkeepingPaperlessError:
            raise
        except Exception:
            raise BookkeepingPaperlessError(
                "Der Paperless-Download konnte nicht ausgeführt werden."
            ) from None

    @staticmethod
    def _response_content_type(response) -> str:
        headers = getattr(response, "headers", None)
        if headers is None:
            return ""
        getter = getattr(headers, "get_content_type", None)
        if callable(getter):
            return str(getter() or "").lower().strip()
        value = headers.get("Content-Type", "") if hasattr(headers, "get") else ""
        return str(value or "").split(";", 1)[0].lower().strip()

    @staticmethod
    def _response_content_length(response) -> int | None:
        headers = getattr(response, "headers", None)
        value = headers.get("Content-Length") if headers is not None else None
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_binary_content_type(content_type: str) -> bool:
        if not content_type:
            return False
        if content_type.startswith("text/"):
            return False
        return content_type in {
            "application/octet-stream",
            "application/pdf",
            "application/x-pdf",
        } or content_type.startswith("image/")

    @classmethod
    def _request_multipart(
        cls,
        *,
        form_fields: list[tuple[str, str]],
        file_name: str,
        file_content: bytes,
    ):
        boundary = f"----QuintusBankStatement{uuid4().hex}"
        body = bytearray()
        for field_name, field_value in form_fields:
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'.encode(
                    "utf-8"
                )
            )
            body.extend(str(field_value).encode("utf-8"))
            body.extend(b"\r\n")
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            (
                f'Content-Disposition: form-data; name="document"; filename="{file_name}"\r\n'
                f"Content-Type: {mimetypes.guess_type(file_name)[0] or 'application/pdf'}\r\n\r\n"
            ).encode("utf-8")
        )
        body.extend(file_content)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        request = Request(
            cls._api_url("documents/post_document/"),
            data=bytes(body),
            headers={
                "Authorization": f"Token {cls._token()}",
                "Accept": "application/json, text/plain, */*",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=cls._timeout()) as response:
                content = response.read()
        except HTTPError as exc:
            logger.warning("Paperless multipart HTTP %s for upload", exc.code)
            raise cls._http_error(exc) from None
        except (URLError, TimeoutError) as exc:
            logger.warning("Paperless multipart connection error: %s", exc)
            raise cls._connection_error(exc) from None
        except Exception:
            logger.exception("Unexpected Paperless multipart error")
            raise BookkeepingPaperlessError(
                "Der PDF-Upload an Paperless konnte nicht ausgeführt werden."
            ) from None
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = content.decode("utf-8", errors="replace").strip().strip('"')
        return payload

    @classmethod
    def _document_id(cls, task: dict) -> int | None:
        candidates = [
            task.get("related_document"),
            task.get("related_document_id"),
            task.get("document_id"),
            task.get("document"),
            task.get("result_data"),
            task.get("result"),
        ]
        for candidate in candidates:
            value = cls._coerce_document_id(candidate)
            if value is not None:
                return value
        return None

    @classmethod
    def _coerce_document_id(cls, candidate) -> int | None:
        decoded_candidate = cls._decode_json_value(candidate)
        if isinstance(decoded_candidate, dict):
            for key in ("id", "document_id", "related_document", "document"):
                value = cls._coerce_document_id(decoded_candidate.get(key))
                if value is not None:
                    return value
            return None
        if isinstance(decoded_candidate, bool):
            return None
        if isinstance(decoded_candidate, int):
            return decoded_candidate if decoded_candidate > 0 else None
        if isinstance(decoded_candidate, str) and decoded_candidate.strip().isdigit():
            value = int(decoded_candidate.strip())
            return value if value > 0 else None
        return None
