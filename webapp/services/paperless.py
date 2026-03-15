from __future__ import annotations

import json
import logging
import mimetypes
import os
from uuid import uuid4
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from django.conf import settings


DEFAULT_TIMEOUT_SECONDS = 10
LOOKUP_PAGE_SIZE = 200
logger = logging.getLogger(__name__)


class PaperlessSearchError(Exception):
    """Benutzerfreundlicher Fehler für die Paperless-Dokumentensuche."""


class PaperlessService:
    @staticmethod
    def base_url() -> str:
        raw_base_url = str(getattr(settings, "PAPERLESS_BASE_URL", "") or "").strip().rstrip("/")
        if raw_base_url.endswith("/api"):
            return raw_base_url[:-4]
        return raw_base_url

    @staticmethod
    def api_token() -> str:
        return str(getattr(settings, "PAPERLESS_API_TOKEN", "") or "").strip()

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.base_url() and cls.api_token())

    @classmethod
    def documents_endpoint(cls) -> str:
        base_url = cls.base_url()
        if not base_url:
            return ""
        return f"{base_url}/api/documents/"

    @classmethod
    def documents_gui_url(
        cls,
        *,
        query: str = "",
        q_liegenschaft: str = "",
        q_einheit: str = "",
        q_mieter: str = "",
        document_type_id: int | None = None,
        sort: str = "",
        reverse: bool = False,
        page: int | None = 1,
    ) -> str:
        base_url = cls.base_url()
        if not base_url:
            return ""

        normalized_query = (query or "").strip()
        normalized_q_liegenschaft = (q_liegenschaft or "").strip()
        normalized_q_einheit = (q_einheit or "").strip()
        normalized_q_mieter = (q_mieter or "").strip()
        normalized_document_type_id = cls._to_int(document_type_id)
        normalized_sort = str(sort or "").strip()
        normalized_page = cls._to_int(page)

        query_params: dict[str, Any] = {}
        if normalized_page is not None and normalized_page > 0:
            query_params["page"] = str(normalized_page)
        if normalized_query:
            query_params["query"] = normalized_query
        custom_field_query = cls._build_gui_custom_field_query(
            q_liegenschaft=normalized_q_liegenschaft,
            q_einheit=normalized_q_einheit,
            q_mieter=normalized_q_mieter,
        )
        if custom_field_query:
            query_params["custom_field_query"] = custom_field_query
        if normalized_document_type_id is not None:
            query_params["document_type__id__in"] = str(normalized_document_type_id)
        if normalized_sort:
            query_params["sort"] = normalized_sort
        if reverse:
            query_params["reverse"] = "1"

        url = f"{base_url}/documents"
        if query_params:
            url = f"{url}?{urlencode(query_params, doseq=True)}"
        return url

    @classmethod
    def document_type_id_by_name(cls, name: str) -> int | None:
        normalized_name = str(name or "").strip().casefold()
        if not normalized_name or not cls.is_configured():
            return None

        document_type_lookup = cls._safe_fetch_lookup_map(endpoint="document_types/")
        for document_type_id, document_type_name in document_type_lookup.items():
            if str(document_type_name or "").strip().casefold() == normalized_name:
                return document_type_id
        return None

    @staticmethod
    def timeout_seconds() -> int:
        raw_timeout = getattr(settings, "PAPERLESS_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        try:
            timeout = int(raw_timeout)
        except (TypeError, ValueError):
            return DEFAULT_TIMEOUT_SECONDS
        if timeout <= 0:
            return DEFAULT_TIMEOUT_SECONDS
        return timeout

    @classmethod
    def search_documents(
        cls,
        *,
        query: str = "",
        q_liegenschaft: str = "",
        q_einheit: str = "",
        q_mieter: str = "",
        tags: list[str] | None = None,
        document_type_id: int | None = None,
        limit: int | None = None,
        sort: str = "",
        reverse: bool = False,
    ) -> list[dict[str, Any]]:
        normalized_query = (query or "").strip()
        normalized_q_liegenschaft = (q_liegenschaft or "").strip()
        normalized_q_einheit = (q_einheit or "").strip()
        normalized_q_mieter = (q_mieter or "").strip()
        normalized_tags = cls._normalize_tag_names(tags)
        normalized_document_type_id = cls._to_int(document_type_id)
        normalized_limit = cls._to_int(limit)
        if normalized_limit is not None and normalized_limit <= 0:
            normalized_limit = None
        normalized_sort = str(sort or "").strip()
        if not any(
            [
                normalized_query,
                normalized_q_liegenschaft,
                normalized_q_einheit,
                normalized_q_mieter,
                normalized_tags,
                normalized_document_type_id,
            ]
        ):
            return []
        if not cls.is_configured():
            raise PaperlessSearchError(
                "Paperless ist noch nicht konfiguriert. "
                "Bitte PAPERLESS_BASE_URL und PAPERLESS_API_TOKEN in der .env setzen."
            )

        tag_lookup = cls._safe_fetch_lookup_map(endpoint="tags/")
        tag_id_by_name = {
            tag_name: tag_id
            for tag_id, tag_name in tag_lookup.items()
        }
        selected_tag_ids = [
            str(tag_id_by_name[tag_name])
            for tag_name in normalized_tags
            if tag_name in tag_id_by_name
        ]
        if normalized_tags and not selected_tag_ids:
            return []

        page_size = LOOKUP_PAGE_SIZE
        if normalized_limit is not None:
            page_size = max(1, min(normalized_limit, LOOKUP_PAGE_SIZE))

        query_params: dict[str, Any] = {"page_size": str(page_size)}
        if normalized_query:
            query_params["query"] = normalized_query
        custom_field_query = cls._build_custom_field_query(
            q_liegenschaft=normalized_q_liegenschaft,
            q_einheit=normalized_q_einheit,
            q_mieter=normalized_q_mieter,
        )
        if custom_field_query:
            query_params["custom_field_query"] = custom_field_query
        if selected_tag_ids:
            query_params["tags__id__all"] = selected_tag_ids
        if normalized_document_type_id is not None:
            query_params["document_type__id__in"] = str(normalized_document_type_id)
        if normalized_sort:
            query_params["sort"] = normalized_sort
        if reverse:
            query_params["reverse"] = "1"

        request_url = cls._build_url(endpoint="documents/", query_params=query_params)
        payload = cls._request_json(request_url)

        if not isinstance(payload, dict):
            raise PaperlessSearchError("Unerwartete Antwort von Paperless (kein JSON-Objekt).")

        raw_results = payload.get("results")
        if raw_results is None:
            available_fields = ", ".join(sorted(payload.keys())[:10]) or "-"
            raise PaperlessSearchError(
                f"Unerwartetes Antwortformat von Paperless. Felder: {available_fields}"
            )
        if not isinstance(raw_results, list):
            raise PaperlessSearchError("Unerwartetes Antwortformat von Paperless (results ist keine Liste).")

        document_type_lookup = cls._safe_fetch_lookup_map(endpoint="document_types/")
        custom_field_name_by_id, custom_field_option_lookup = cls._safe_fetch_custom_field_metadata()
        custom_field_id_by_name = {
            field_name: field_id
            for field_id, field_name in custom_field_name_by_id.items()
        }

        documents: list[dict[str, Any]] = []
        for raw_document in raw_results:
            if not isinstance(raw_document, dict):
                continue
            documents.append(
                cls._normalize_document(
                    raw_document,
                    document_type_lookup=document_type_lookup,
                    tag_lookup=tag_lookup,
                    custom_field_id_by_name=custom_field_id_by_name,
                    custom_field_name_by_id=custom_field_name_by_id,
                    custom_field_option_lookup=custom_field_option_lookup,
                )
            )
        if normalized_limit is not None:
            return documents[:normalized_limit]
        return documents

    @classmethod
    def list_tags(cls) -> list[dict[str, str]]:
        if not cls.is_configured():
            return []
        lookup = cls._safe_fetch_lookup_map(endpoint="tags/")
        return [
            {"id": str(tag_id), "name": tag_name}
            for tag_id, tag_name in sorted(
                lookup.items(),
                key=lambda item: item[1].lower(),
            )
        ]

    @classmethod
    def download_document(cls, *, document_id: int) -> tuple[bytes, str, str]:
        if not cls.is_configured():
            raise PaperlessSearchError(
                "Paperless ist noch nicht konfiguriert. "
                "Bitte PAPERLESS_BASE_URL und PAPERLESS_API_TOKEN in der .env setzen."
            )

        request_url = cls._build_url(endpoint=f"documents/{int(document_id)}/download/")
        request = Request(
            request_url,
            headers={
                "Authorization": f"Token {cls.api_token()}",
                "Accept": "*/*",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=cls.timeout_seconds()) as response:
                content = response.read()
                content_type = response.headers.get_content_type() or "application/octet-stream"
                filename = response.headers.get_filename() or f"paperless_{int(document_id)}"
                return content, content_type, filename
        except HTTPError as exc:
            logger.warning("Paperless download failed with HTTP %s for %s", exc.code, request_url)
            if exc.code in {401, 403}:
                raise PaperlessSearchError(
                    "Zugriff auf Paperless wurde abgelehnt. Bitte API-Token prüfen."
                ) from None
            if exc.code == 404:
                raise PaperlessSearchError("Dokument wurde in Paperless nicht gefunden.") from None
            raise PaperlessSearchError(
                f"Paperless antwortet mit HTTP-Status {exc.code}."
            ) from None
        except URLError:
            logger.warning("Paperless host not reachable for %s", request_url)
            raise PaperlessSearchError(
                "Paperless ist nicht erreichbar. Bitte Basis-URL und Netzwerk prüfen."
            ) from None
        except TimeoutError:
            logger.warning("Paperless download timeout for %s", request_url)
            raise PaperlessSearchError("Zeitüberschreitung bei der Anfrage an Paperless.") from None
        except Exception:
            logger.exception("Paperless download failed unexpectedly for %s", request_url)
            raise PaperlessSearchError("Paperless-Dokument konnte nicht geladen werden.") from None

    @classmethod
    def upload_document(
        cls,
        *,
        uploaded_file,
        title: str = "",
        description: str = "",
        q_liegenschaft: str = "",
        q_einheit: str = "",
        q_mieter: str = "",
        tags: list[str] | None = None,
    ) -> str:
        if not cls.is_configured():
            raise PaperlessSearchError(
                "Paperless ist noch nicht konfiguriert. "
                "Bitte PAPERLESS_BASE_URL und PAPERLESS_API_TOKEN in der .env setzen."
            )

        normalized_tags = cls._normalize_tag_names(tags)
        normalized_title = str(title or "").strip()
        normalized_description = str(description or "").strip()

        tag_lookup = cls._fetch_lookup_map(endpoint="tags/")
        tag_id_by_name = {
            tag_name: tag_id
            for tag_id, tag_name in tag_lookup.items()
        }
        tag_ids: list[str] = []
        for tag_name in normalized_tags:
            tag_id = tag_id_by_name.get(tag_name)
            if tag_id is None:
                raise PaperlessSearchError(f"Tag '{tag_name}' wurde in Paperless nicht gefunden.")
            tag_ids.append(str(tag_id))

        custom_field_name_by_id, _custom_field_option_lookup = cls._fetch_custom_field_metadata()
        custom_field_id_by_name = {
            field_name: field_id
            for field_id, field_name in custom_field_name_by_id.items()
        }
        custom_fields_payload: dict[str, str] = {}
        for field_name, value in (
            ("q_liegenschaft", q_liegenschaft),
            ("q_einheit", q_einheit),
            ("q_mieter", q_mieter),
        ):
            normalized_value = str(value or "").strip()
            if not normalized_value:
                continue
            field_id = custom_field_id_by_name.get(field_name)
            if field_id is None:
                raise PaperlessSearchError(
                    f"Custom Field '{field_name}' fehlt in Paperless."
                )
            custom_fields_payload[str(field_id)] = normalized_value

        request_url = cls._build_url(endpoint="documents/post_document/")
        form_fields: list[tuple[str, str]] = []
        if normalized_title:
            form_fields.append(("title", normalized_title))
        if normalized_description:
            form_fields.append(("notes", normalized_description))
        for tag_id in tag_ids:
            form_fields.append(("tags", tag_id))
        if custom_fields_payload:
            form_fields.append(
                ("custom_fields", json.dumps(custom_fields_payload, ensure_ascii=False))
            )

        response_bytes = cls._request_multipart(
            request_url=request_url,
            form_fields=form_fields,
            file_field_name="document",
            uploaded_file=uploaded_file,
        )
        task_id = cls._parse_upload_response(response_bytes)
        if not task_id:
            raise PaperlessSearchError("Paperless hat keine Task-ID für den Upload zurückgegeben.")
        return task_id

    @classmethod
    def _request_json(cls, request_url: str) -> Any:
        request = Request(
            request_url,
            headers={
                "Authorization": f"Token {cls.api_token()}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=cls.timeout_seconds()) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            logger.warning("Paperless request failed with HTTP %s for %s", exc.code, request_url)
            if exc.code in {401, 403}:
                raise PaperlessSearchError(
                    "Zugriff auf Paperless wurde abgelehnt. Bitte API-Token prüfen."
                ) from None
            raise PaperlessSearchError(
                f"Paperless antwortet mit HTTP-Status {exc.code}."
            ) from None
        except URLError:
            logger.warning("Paperless host not reachable for %s", request_url)
            raise PaperlessSearchError(
                "Paperless ist nicht erreichbar. Bitte Basis-URL und Netzwerk prüfen."
            ) from None
        except TimeoutError:
            logger.warning("Paperless request timeout for %s", request_url)
            raise PaperlessSearchError("Zeitüberschreitung bei der Anfrage an Paperless.") from None
        except json.JSONDecodeError:
            logger.warning("Paperless returned non-JSON payload for %s", request_url)
            raise PaperlessSearchError("Ungültige Antwort von Paperless erhalten.") from None
        except Exception:
            logger.exception("Paperless request failed unexpectedly for %s", request_url)
            raise PaperlessSearchError("Paperless-Suche konnte nicht ausgeführt werden.") from None

    @classmethod
    def _request_multipart(
        cls,
        *,
        request_url: str,
        form_fields: list[tuple[str, str]],
        file_field_name: str,
        uploaded_file,
    ) -> bytes:
        boundary = f"----QuintusPaperless{uuid4().hex}"
        file_name = os.path.basename(getattr(uploaded_file, "name", "") or "upload.bin")
        content_type = (
            str(getattr(uploaded_file, "content_type", "") or "").strip()
            or mimetypes.guess_type(file_name)[0]
            or "application/octet-stream"
        )
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)

        body = bytearray()
        for field_name, field_value in form_fields:
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'.encode("utf-8")
            )
            body.extend(str(field_value).encode("utf-8"))
            body.extend(b"\r\n")

        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            (
                f'Content-Disposition: form-data; name="{file_field_name}"; '
                f'filename="{file_name}"\r\n'
            ).encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(file_bytes)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        request = Request(
            request_url,
            data=bytes(body),
            headers={
                "Authorization": f"Token {cls.api_token()}",
                "Accept": "application/json, text/plain, */*",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=cls.timeout_seconds()) as response:
                return response.read()
        except HTTPError as exc:
            logger.warning("Paperless multipart request failed with HTTP %s for %s", exc.code, request_url)
            if exc.code in {401, 403}:
                raise PaperlessSearchError(
                    "Zugriff auf Paperless wurde abgelehnt. Bitte API-Token prüfen."
                ) from None
            raise PaperlessSearchError(
                f"Paperless antwortet mit HTTP-Status {exc.code}."
            ) from None
        except URLError:
            logger.warning("Paperless host not reachable for %s", request_url)
            raise PaperlessSearchError(
                "Paperless ist nicht erreichbar. Bitte Basis-URL und Netzwerk prüfen."
            ) from None
        except TimeoutError:
            logger.warning("Paperless multipart request timeout for %s", request_url)
            raise PaperlessSearchError("Zeitüberschreitung bei der Anfrage an Paperless.") from None
        except Exception:
            logger.exception("Paperless multipart request failed unexpectedly for %s", request_url)
            raise PaperlessSearchError("Paperless-Upload konnte nicht ausgeführt werden.") from None

    @classmethod
    def _parse_upload_response(cls, response_bytes: bytes) -> str:
        response_text = response_bytes.decode("utf-8", errors="replace").strip()
        if not response_text:
            return ""
        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError:
            return response_text.strip('"')

        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, dict):
            for key in ("task_id", "task", "id", "uuid"):
                value = payload.get(key)
                if value is not None:
                    return str(value).strip()
        return response_text.strip('"')

    @classmethod
    def _build_url(cls, *, endpoint: str, query_params: dict[str, Any] | None = None) -> str:
        base_url = cls.base_url()
        if not base_url:
            return ""
        endpoint_path = endpoint.lstrip("/")
        url = f"{base_url}/api/{endpoint_path}"
        if query_params:
            url = f"{url}?{urlencode(query_params, doseq=True)}"
        return url

    @classmethod
    def _build_custom_field_query(
        cls,
        *,
        q_liegenschaft: str,
        q_einheit: str,
        q_mieter: str,
    ) -> str:
        predicates: list[list[str]] = []
        if q_liegenschaft:
            predicates.append(["q_liegenschaft", "exact", q_liegenschaft])
        if q_einheit:
            predicates.append(["q_einheit", "exact", q_einheit])
        if q_mieter:
            predicates.append(["q_mieter", "contains", q_mieter])
        if not predicates:
            return ""
        if len(predicates) == 1:
            return json.dumps(predicates[0], ensure_ascii=False, separators=(",", ":"))
        return json.dumps(["AND", predicates], ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def _build_gui_custom_field_query(
        cls,
        *,
        q_liegenschaft: str,
        q_einheit: str,
        q_mieter: str,
    ) -> str:
        raw_filters = [
            ("q_liegenschaft", str(q_liegenschaft or "").strip(), "exact", False),
            ("q_einheit", str(q_einheit or "").strip(), "exact", False),
            ("q_mieter", str(q_mieter or "").strip(), "contains", True),
        ]
        raw_filters = [item for item in raw_filters if item[1]]
        if not raw_filters or not cls.is_configured():
            return ""

        custom_field_name_by_id, custom_field_option_lookup = cls._safe_fetch_custom_field_metadata()
        custom_field_id_by_name = {
            field_name: field_id
            for field_id, field_name in custom_field_name_by_id.items()
        }

        predicates: list[list[Any]] = []
        for field_name, raw_value, operator, allow_multiple_labels in raw_filters:
            field_id = custom_field_id_by_name.get(field_name)
            if field_id is None:
                continue

            option_ids = cls._match_custom_field_option_ids(
                field_name=field_name,
                raw_value=raw_value,
                custom_field_option_lookup=custom_field_option_lookup,
                allow_multiple_labels=allow_multiple_labels,
            )
            if option_ids:
                predicates.append([field_id, "in", option_ids])
                continue

            predicates.append([field_id, operator, raw_value])

        if not predicates:
            return ""
        combinator = "OR" if len(predicates) == 1 else "AND"
        return json.dumps([combinator, predicates], ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def _match_custom_field_option_ids(
        cls,
        *,
        field_name: str,
        raw_value: str,
        custom_field_option_lookup: dict[str, dict[str, str]],
        allow_multiple_labels: bool,
    ) -> list[str]:
        options = custom_field_option_lookup.get(field_name) or {}
        if not options:
            return []

        candidate_labels = [str(raw_value or "").strip()]
        if allow_multiple_labels:
            candidate_labels = [
                part.strip()
                for part in str(raw_value or "").split(",")
                if part.strip()
            ] or candidate_labels

        normalized_labels = {
            label.casefold(): label
            for label in candidate_labels
        }
        matched_option_ids: list[str] = []
        for option_id, option_label in options.items():
            option_label_text = str(option_label or "").strip()
            if not option_label_text:
                continue
            if option_label_text.casefold() not in normalized_labels:
                continue
            option_id_text = str(option_id or "").strip()
            if option_id_text and option_id_text not in matched_option_ids:
                matched_option_ids.append(option_id_text)
        return matched_option_ids

    @classmethod
    def _safe_fetch_lookup_map(cls, *, endpoint: str) -> dict[int, str]:
        try:
            return cls._fetch_lookup_map(endpoint=endpoint)
        except PaperlessSearchError as exc:
            logger.warning("Paperless lookup '%s' fehlgeschlagen: %s", endpoint, exc)
            return {}

    @classmethod
    def _fetch_lookup_map(cls, *, endpoint: str) -> dict[int, str]:
        lookup: dict[int, str] = {}
        next_url = cls._build_url(
            endpoint=endpoint,
            query_params={"page_size": str(LOOKUP_PAGE_SIZE)},
        )
        while next_url:
            payload = cls._request_json(next_url)
            if not isinstance(payload, dict):
                break

            raw_results = payload.get("results")
            if not isinstance(raw_results, list):
                break
            for item in raw_results:
                if not isinstance(item, dict):
                    continue
                item_id = cls._to_int(item.get("id"))
                item_name = str(item.get("name") or "").strip()
                if item_id is None or not item_name:
                    continue
                lookup[item_id] = item_name

            raw_next = payload.get("next")
            if isinstance(raw_next, str) and raw_next.strip():
                next_url = urljoin(f"{cls.base_url()}/", raw_next.strip())
            else:
                next_url = ""
        return lookup

    @classmethod
    def _safe_fetch_custom_field_metadata(cls) -> tuple[dict[int, str], dict[str, dict[str, str]]]:
        try:
            return cls._fetch_custom_field_metadata()
        except PaperlessSearchError as exc:
            logger.warning("Paperless custom_fields lookup fehlgeschlagen: %s", exc)
            return {}, {}

    @classmethod
    def _fetch_custom_field_metadata(cls) -> tuple[dict[int, str], dict[str, dict[str, str]]]:
        name_by_id: dict[int, str] = {}
        option_lookup: dict[str, dict[str, str]] = {}

        next_url = cls._build_url(
            endpoint="custom_fields/",
            query_params={"page_size": str(LOOKUP_PAGE_SIZE)},
        )
        while next_url:
            payload = cls._request_json(next_url)
            if not isinstance(payload, dict):
                break

            raw_results = payload.get("results")
            if not isinstance(raw_results, list):
                break

            for item in raw_results:
                if not isinstance(item, dict):
                    continue
                field_id = cls._to_int(item.get("id"))
                field_name = str(item.get("name") or "").strip()
                if field_id is not None and field_name:
                    name_by_id[field_id] = field_name
                    options = cls._extract_custom_field_options(item)
                    if options:
                        option_lookup[field_name] = options

            raw_next = payload.get("next")
            if isinstance(raw_next, str) and raw_next.strip():
                next_url = urljoin(f"{cls.base_url()}/", raw_next.strip())
            else:
                next_url = ""

        return name_by_id, option_lookup

    @classmethod
    def _normalize_document(
        cls,
        raw_document: dict[str, Any],
        *,
        document_type_lookup: dict[int, str],
        tag_lookup: dict[int, str],
        custom_field_id_by_name: dict[str, int],
        custom_field_name_by_id: dict[int, str],
        custom_field_option_lookup: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        raw_id = raw_document.get("id")
        if raw_id is None or raw_id == "":
            document_id = "-"
        else:
            document_id = str(raw_id)

        title = str(raw_document.get("title") or "").strip() or "(Ohne Titel)"
        created = cls._normalize_created(raw_document.get("created"))
        document_type = cls._resolve_document_type(
            raw_document=raw_document,
            document_type_lookup=document_type_lookup,
        )
        tags = cls._resolve_tags(
            raw_document=raw_document,
            tag_lookup=tag_lookup,
        )
        custom_field_values = cls._extract_custom_field_values(
            raw_document=raw_document,
            custom_field_name_by_id=custom_field_name_by_id,
        )
        q_liegenschaft = custom_field_values.get("q_liegenschaft", "-")
        q_einheit = custom_field_values.get("q_einheit", "-")
        q_mieter = custom_field_values.get("q_mieter", "-")

        # Fallback, falls Paperless die Werte getrennt unter custom_field_values liefert.
        raw_custom_field_values = raw_document.get("custom_field_values")
        if isinstance(raw_custom_field_values, dict):
            q_liegenschaft_id = custom_field_id_by_name.get("q_liegenschaft")
            q_einheit_id = custom_field_id_by_name.get("q_einheit")
            q_mieter_id = custom_field_id_by_name.get("q_mieter")
            if q_liegenschaft_id is not None and q_liegenschaft == "-":
                q_liegenschaft = cls._value_to_text(
                    raw_custom_field_values.get(q_liegenschaft_id)
                    or raw_custom_field_values.get(str(q_liegenschaft_id))
                )
            if q_einheit_id is not None and q_einheit == "-":
                q_einheit = cls._value_to_text(
                    raw_custom_field_values.get(q_einheit_id)
                    or raw_custom_field_values.get(str(q_einheit_id))
                )
            if q_mieter_id is not None and q_mieter == "-":
                q_mieter = cls._value_to_text(
                    raw_custom_field_values.get(q_mieter_id)
                    or raw_custom_field_values.get(str(q_mieter_id))
                )

        q_liegenschaft = cls._translate_custom_field_value(
            field_name="q_liegenschaft",
            value=q_liegenschaft,
            custom_field_option_lookup=custom_field_option_lookup,
        )
        q_einheit = cls._translate_custom_field_value(
            field_name="q_einheit",
            value=q_einheit,
            custom_field_option_lookup=custom_field_option_lookup,
        )
        q_mieter = cls._translate_custom_field_value(
            field_name="q_mieter",
            value=q_mieter,
            custom_field_option_lookup=custom_field_option_lookup,
        )

        score = cls._normalize_score(raw_document)

        return {
            "id": document_id,
            "title": title,
            "created": created,
            "document_type": document_type,
            "tags": tags,
            "q_liegenschaft": q_liegenschaft,
            "q_einheit": q_einheit,
            "q_mieter": q_mieter,
            "score": score,
        }

    @classmethod
    def _resolve_document_type(
        cls,
        *,
        raw_document: dict[str, Any],
        document_type_lookup: dict[int, str],
    ) -> str:
        raw_document_type = raw_document.get("document_type")
        if isinstance(raw_document_type, dict):
            type_name = str(raw_document_type.get("name") or "").strip()
            if type_name:
                return type_name
            raw_document_type = raw_document_type.get("id")

        type_id = cls._to_int(raw_document_type)
        if type_id is not None:
            return document_type_lookup.get(type_id, str(type_id))

        type_name = str(
            raw_document.get("document_type_name")
            or raw_document.get("document_type__name")
            or ""
        ).strip()
        return type_name or "-"

    @classmethod
    def _resolve_tags(
        cls,
        *,
        raw_document: dict[str, Any],
        tag_lookup: dict[int, str],
    ) -> str:
        raw_tags = raw_document.get("tags")
        if not isinstance(raw_tags, list):
            return "-"

        tag_names: list[str] = []
        for tag_entry in raw_tags:
            if isinstance(tag_entry, dict):
                name = str(tag_entry.get("name") or "").strip()
                if name:
                    tag_names.append(name)
                    continue
                tag_id = cls._to_int(tag_entry.get("id"))
                if tag_id is not None:
                    tag_names.append(tag_lookup.get(tag_id, str(tag_id)))
                continue

            tag_id = cls._to_int(tag_entry)
            if tag_id is not None:
                tag_names.append(tag_lookup.get(tag_id, str(tag_id)))
                continue

            text = str(tag_entry or "").strip()
            if text:
                tag_names.append(text)

        tag_names = [name for name in tag_names if name]
        if not tag_names:
            return "-"
        return ", ".join(tag_names)

    @classmethod
    def _extract_custom_field_values(
        cls,
        *,
        raw_document: dict[str, Any],
        custom_field_name_by_id: dict[int, str],
    ) -> dict[str, str]:
        values: dict[str, str] = {}
        raw_custom_fields = raw_document.get("custom_fields")

        if isinstance(raw_custom_fields, dict):
            for key, value in raw_custom_fields.items():
                key_text = str(key or "").strip()
                if not key_text:
                    continue
                values[key_text] = cls._value_to_text(value)

        if isinstance(raw_custom_fields, list):
            for field_entry in raw_custom_fields:
                if not isinstance(field_entry, dict):
                    continue
                field_name = str(field_entry.get("name") or "").strip()
                field_id = None
                field_value = field_entry.get("value")

                if not field_name:
                    raw_field = field_entry.get("field")
                    if isinstance(raw_field, dict):
                        field_name = str(raw_field.get("name") or "").strip()
                        field_id = cls._to_int(raw_field.get("id"))
                    else:
                        field_id = cls._to_int(raw_field)

                if not field_name and field_id is not None:
                    field_name = custom_field_name_by_id.get(field_id, "")

                if field_name:
                    values[field_name] = cls._value_to_text(field_value)

        for field_name in ("q_liegenschaft", "q_einheit", "q_mieter"):
            if field_name not in values and raw_document.get(field_name) is not None:
                values[field_name] = cls._value_to_text(raw_document.get(field_name))

        return values

    @classmethod
    def _translate_custom_field_value(
        cls,
        *,
        field_name: str,
        value: str,
        custom_field_option_lookup: dict[str, dict[str, str]],
    ) -> str:
        normalized_value = str(value or "").strip()
        if not normalized_value or normalized_value == "-":
            return "-"
        options = custom_field_option_lookup.get(field_name) or {}
        return options.get(normalized_value, normalized_value)

    @classmethod
    def _extract_custom_field_options(cls, raw_custom_field: dict[str, Any]) -> dict[str, str]:
        option_map: dict[str, str] = {}
        candidate_keys = (
            "select_options",
            "choices",
            "extra_data",
            "data",
            "configuration",
            "settings",
        )

        for key in candidate_keys:
            candidate = raw_custom_field.get(key)
            cls._collect_option_pairs(candidate, option_map)
        cls._collect_option_pairs(raw_custom_field, option_map)
        return option_map

    @classmethod
    def _collect_option_pairs(cls, candidate: Any, option_map: dict[str, str]) -> None:
        if isinstance(candidate, list):
            for item in candidate:
                cls._collect_option_pairs(item, option_map)
            return

        if not isinstance(candidate, dict):
            return

        id_candidate = candidate.get("id")
        value_candidate = candidate.get("value")
        label_candidate = (
            candidate.get("label")
            or candidate.get("name")
            or candidate.get("title")
        )
        if label_candidate is not None:
            option_key = str(id_candidate if id_candidate is not None else value_candidate or "").strip()
            option_label = str(label_candidate).strip()
            if option_key and option_label:
                option_map.setdefault(option_key, option_label)

        for key, value in candidate.items():
            key_text = str(key or "").strip()
            if isinstance(value, str):
                value_text = value.strip()
                if key_text and value_text and key_text not in {
                    "name",
                    "label",
                    "title",
                    "type",
                    "description",
                    "help_text",
                    "placeholder",
                }:
                    option_map.setdefault(key_text, value_text)
            else:
                cls._collect_option_pairs(value, option_map)

    @staticmethod
    def _normalize_created(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return "-"
        if "T" in text:
            text = text.split("T", 1)[0]
        if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
            return text[:10]
        return text

    @staticmethod
    def _normalize_score(raw_document: dict[str, Any]) -> str:
        score_value: Any = None
        search_hit = raw_document.get("__search_hit__")
        if isinstance(search_hit, dict):
            score_value = search_hit.get("score")
            if score_value is None:
                score_value = search_hit.get("rank")
        if score_value is None:
            score_value = raw_document.get("score")

        if isinstance(score_value, (int, float)):
            return f"{score_value:.3f}"
        score_text = str(score_value or "").strip()
        return score_text or "-"

    @classmethod
    def _value_to_text(cls, value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, list):
            parts = [
                cls._value_to_text(item)
                for item in value
            ]
            compact_parts = [part for part in parts if part and part != "-"]
            return ", ".join(compact_parts) if compact_parts else "-"
        if isinstance(value, dict):
            for key in ("name", "label", "value", "title"):
                if key in value:
                    return cls._value_to_text(value.get(key))
            rendered = json.dumps(value, ensure_ascii=False)
            return rendered or "-"
        text = str(value).strip()
        return text or "-"

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_tag_names(tags: list[str] | None) -> list[str]:
        normalized_tags: list[str] = []
        for raw_tag in tags or []:
            tag_name = str(raw_tag or "").strip()
            if tag_name and tag_name not in normalized_tags:
                normalized_tags.append(tag_name)
        return normalized_tags
