from __future__ import annotations

import json
import mimetypes
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from uuid import uuid4

from django.conf import settings


class BookkeepingPaperlessError(Exception):
    """User-facing Paperless error without response or credential details."""


class PaperlessClient:
    CORRESPONDENT_NAME = "Erste Bank"
    DOCUMENT_TYPE_NAME = "Kontoauszug"
    TAG_NAMES = ("Buchhaltung", "Immo-Fuchs KG")
    STORAGE_PATH_NAME = "IFKG Kontoauszüge"
    MANUAL_CORRESPONDENT_NAME = "Diverse"
    MANUAL_DOCUMENT_TYPE_NAME = "Eingangsrechnung"
    MANUAL_STORAGE_PATH_NAME = "IFKG Eingangsrechnungen"
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
            if exc.code in {401, 403}:
                raise BookkeepingPaperlessError(
                    "Paperless hat den Zugriff abgelehnt. Bitte den API-Token prüfen."
                ) from None
            raise BookkeepingPaperlessError(
                f"Paperless antwortet mit HTTP-Status {exc.code}."
            ) from None
        except (URLError, TimeoutError):
            raise BookkeepingPaperlessError(
                "Paperless ist nicht erreichbar oder die Anfrage hat zu lange gedauert."
            ) from None
        except Exception:
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
    def _find_exact_name(cls, endpoint: str, name: str) -> int | None:
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
        for item in results:
            if not isinstance(item, dict) or item.get("name") != name:
                continue
            try:
                return int(item["id"])
            except (KeyError, TypeError, ValueError):
                continue
        return None

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
    def _require_storage_path(cls) -> int:
        existing_id = cls._find_exact_name("storage_paths/", cls.STORAGE_PATH_NAME)
        if existing_id is not None:
            return existing_id
        raise BookkeepingPaperlessError(
            f"Der Paperless-Speicherpfad '{cls.STORAGE_PATH_NAME}' fehlt. "
            "Bitte zuerst exakt unter diesem Namen anlegen."
        )

    @classmethod
    def upload_bank_statement(cls, statement) -> str:
        if not cls.is_configured():
            raise BookkeepingPaperlessError(
                "Paperless ist nicht konfiguriert. Bitte die Paperless-Verbindung prüfen."
            )
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
        title = (
            f"Kontoauszug {statement.booking_month} – {statement.iban}"
        )
        form_fields = [
            ("title", title),
            ("created", statement.statement_date.isoformat()),
            ("correspondent", str(correspondent_id)),
            ("document_type", str(document_type_id)),
            ("storage_path", str(storage_path_id)),
            *[("tags", str(tag_id)) for tag_id in tag_ids],
            (
                "custom_fields",
                json.dumps(
                    {
                        str(custom_field_ids["q_buchungsdatum"]): statement.statement_date.isoformat(),
                        str(custom_field_ids["q_buchungsmonat"]): statement.booking_month,
                        str(custom_field_ids["q_buchungsquartal"]): statement.booking_quarter,
                        str(custom_field_ids["q_bookkeeping_referenz"]): str(
                            statement.reference_uuid
                        ),
                    },
                    ensure_ascii=False,
                ),
            ),
        ]
        try:
            with statement.temporary_pdf.open("rb") as pdf_file:
                response = cls._request_multipart(
                    form_fields=form_fields,
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
        correspondent_id = cls._require_named(
            "correspondents/", cls.MANUAL_CORRESPONDENT_NAME
        )
        document_type_id = cls._require_named(
            "document_types/", cls.MANUAL_DOCUMENT_TYPE_NAME
        )
        tag_ids = [
            cls._require_named("tags/", tag_name) for tag_name in cls.TAG_NAMES
        ]
        storage_path_id = cls._find_exact_name(
            "storage_paths/", cls.MANUAL_STORAGE_PATH_NAME
        )
        if storage_path_id is None:
            raise BookkeepingPaperlessError(
                f"Der Paperless-Speicherpfad '{cls.MANUAL_STORAGE_PATH_NAME}' fehlt. "
                "Bitte zuerst exakt unter diesem Namen anlegen."
            )
        custom_field_ids = {
            name: cls._require_custom_field(name, data_type)
            for name, data_type in cls.CUSTOM_FIELDS.items()
        }
        payment_date = invoice.payment_date
        if payment_date is None:
            raise BookkeepingPaperlessError(
                "Für die Paperless-Übertragung fehlt das Zahlungsdatum."
            )
        title = (
            f"Eingangsrechnung {invoice.invoice_number or 'ohne Rechnungsnummer'}"
            f" – {invoice.partner_name or 'Diverse'}"
        )
        booking_month = payment_date.strftime("%Y-%m")
        booking_quarter = (
            f"{payment_date.year}-Q{((payment_date.month - 1) // 3) + 1}"
        )
        form_fields = [
            ("title", title),
            ("created", (invoice.invoice_date or payment_date).isoformat()),
            ("correspondent", str(correspondent_id)),
            ("document_type", str(document_type_id)),
            ("storage_path", str(storage_path_id)),
            *[("tags", str(tag_id)) for tag_id in tag_ids],
            (
                "custom_fields",
                json.dumps(
                    {
                        str(custom_field_ids["q_buchungsdatum"]): payment_date.isoformat(),
                        str(custom_field_ids["q_buchungsmonat"]): booking_month,
                        str(custom_field_ids["q_buchungsquartal"]): booking_quarter,
                        str(custom_field_ids["q_bookkeeping_referenz"]): str(
                            invoice.reference_uuid
                        ),
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
        document_id = cls._document_id(task)
        if document_id is not None:
            return {
                "status": "completed",
                "document_id": document_id,
                "message": "",
                "found": True,
            }
        raw_status = cls._normalize_task_status(task)
        if raw_status in {"failure", "failed"}:
            return {
                "status": "failed",
                "document_id": None,
                "message": cls._task_error_message(task),
                "found": True,
            }
        if raw_status in {"pending", "started", "retry", "running"}:
            return {
                "status": "pending",
                "document_id": None,
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
            return {"status": "pending", "document_id": None, "message": ""}
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
        return {"status": "completed", "document_id": document_id, "message": ""}

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
    ):
        if isinstance(custom_fields, dict):
            updated = dict(custom_fields)
            for key in list(updated):
                if str(key) == str(field_id) or str(key) == field_name:
                    updated[key] = value
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
        raise BookkeepingPaperlessError(
            f"Das Paperless-Dokument enthält kein '{field_name}'-Feld."
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
        candidates = [task.get("message"), task.get("error"), task.get("detail")]
        result = cls._decode_json_value(task.get("result"))
        if isinstance(result, dict):
            candidates.extend(
                [result.get("message"), result.get("error"), result.get("detail")]
            )
        for candidate in candidates:
            message = str(candidate or "").strip()
            if message:
                return message
        return "Paperless meldet einen Fehler beim Upload."

    @classmethod
    def document_url(cls, document_id: int | None) -> str:
        if document_id is None or not cls.base_url():
            return ""
        return urljoin(f"{cls.base_url()}/", f"documents/{int(document_id)}/")

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
            if exc.code in {401, 403}:
                raise BookkeepingPaperlessError(
                    "Paperless hat den Zugriff abgelehnt. Bitte den API-Token prüfen."
                ) from None
            raise BookkeepingPaperlessError(
                f"Paperless antwortet mit HTTP-Status {exc.code}."
            ) from None
        except (URLError, TimeoutError):
            raise BookkeepingPaperlessError(
                "Paperless ist nicht erreichbar oder die Anfrage hat zu lange gedauert."
            ) from None
        except Exception:
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
