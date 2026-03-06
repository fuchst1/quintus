from __future__ import annotations

import json
import logging
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
    ) -> list[dict[str, Any]]:
        normalized_query = (query or "").strip()
        normalized_q_liegenschaft = (q_liegenschaft or "").strip()
        normalized_q_einheit = (q_einheit or "").strip()
        if not any([normalized_query, normalized_q_liegenschaft, normalized_q_einheit]):
            return []
        if not cls.is_configured():
            raise PaperlessSearchError(
                "Paperless ist noch nicht konfiguriert. "
                "Bitte PAPERLESS_BASE_URL und PAPERLESS_API_TOKEN in der .env setzen."
            )

        query_params: dict[str, str] = {}
        if normalized_query:
            query_params["query"] = normalized_query
        custom_field_query = cls._build_custom_field_query(
            q_liegenschaft=normalized_q_liegenschaft,
            q_einheit=normalized_q_einheit,
        )
        if custom_field_query:
            query_params["custom_field_query"] = custom_field_query

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
        tag_lookup = cls._safe_fetch_lookup_map(endpoint="tags/")
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
        return documents

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
    def _build_url(cls, *, endpoint: str, query_params: dict[str, str] | None = None) -> str:
        base_url = cls.base_url()
        if not base_url:
            return ""
        endpoint_path = endpoint.lstrip("/")
        url = f"{base_url}/api/{endpoint_path}"
        if query_params:
            url = f"{url}?{urlencode(query_params)}"
        return url

    @classmethod
    def _build_custom_field_query(cls, *, q_liegenschaft: str, q_einheit: str) -> str:
        predicates: list[list[str]] = []
        if q_liegenschaft:
            predicates.append(["q_liegenschaft", "exact", q_liegenschaft])
        if q_einheit:
            predicates.append(["q_einheit", "exact", q_einheit])
        if not predicates:
            return ""
        if len(predicates) == 1:
            return json.dumps(predicates[0], ensure_ascii=False, separators=(",", ":"))
        return json.dumps(["AND", predicates], ensure_ascii=False, separators=(",", ":"))

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

        # Fallback, falls Paperless die Werte getrennt unter custom_field_values liefert.
        raw_custom_field_values = raw_document.get("custom_field_values")
        if isinstance(raw_custom_field_values, dict):
            q_liegenschaft_id = custom_field_id_by_name.get("q_liegenschaft")
            q_einheit_id = custom_field_id_by_name.get("q_einheit")
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

        score = cls._normalize_score(raw_document)

        return {
            "id": document_id,
            "title": title,
            "created": created,
            "document_type": document_type,
            "tags": tags,
            "q_liegenschaft": q_liegenschaft,
            "q_einheit": q_einheit,
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

        for field_name in ("q_liegenschaft", "q_einheit"):
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
