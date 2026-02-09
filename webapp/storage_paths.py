import os
import posixpath
import uuid

from django.utils import timezone
from django.utils.text import slugify


def _safe_slug(value: str, fallback: str) -> str:
    slug = slugify((value or "").strip())
    return slug or fallback


def _split_filename(filename: str) -> tuple[str, str]:
    base, ext = os.path.splitext(filename or "")
    safe_base = _safe_slug(base, "datei")
    safe_ext = (ext or "").lower()
    return safe_base, safe_ext


def _resolve_entity_context(instance) -> tuple[str, str]:
    explicit_entity_type = getattr(instance, "_upload_entity_type", "")
    explicit_entity_id = getattr(instance, "_upload_entity_id", "")
    if explicit_entity_type and explicit_entity_id:
        return _safe_slug(str(explicit_entity_type), "objekt"), str(explicit_entity_id)

    explicit_object = getattr(instance, "_upload_content_object", None)
    if explicit_object is not None and getattr(explicit_object, "pk", None) is not None:
        return (
            _safe_slug(getattr(explicit_object._meta, "model_name", "objekt"), "objekt"),
            str(explicit_object.pk),
        )

    if getattr(instance, "pk", None) is None:
        return "unzugeordnet", "0"

    zuordnungen = getattr(instance, "zuordnungen", None)
    if zuordnungen is None:
        return "unzugeordnet", "0"
    zuordnung = zuordnungen.select_related("content_type").order_by("id").first()
    if zuordnung is None or not zuordnung.content_type_id or not zuordnung.object_id:
        return "unzugeordnet", "0"
    entity_type = _safe_slug(zuordnung.content_type.model, "objekt")
    entity_id = str(zuordnung.object_id)
    return entity_type, entity_id


def datei_upload_to(instance, filename: str) -> str:
    entity_type, entity_id = _resolve_entity_context(instance)
    category = _safe_slug(getattr(instance, "kategorie", "") or "sonstiges", "sonstiges")
    now = timezone.now()
    safe_base, safe_ext = _split_filename(filename)
    unique_name = f"{uuid.uuid4().hex}_{safe_base}{safe_ext}"
    return (
        f"uploads/{entity_type}/{entity_id}/{category}/"
        f"{now:%Y}/{now:%m}/{unique_name}"
    )


def build_derived_upload_path(
    original_upload_path: str,
    derivative_kind: str,
    *,
    filename: str | None = None,
) -> str:
    original = (original_upload_path or "").lstrip("/")
    if original.startswith("uploads/"):
        original = original[len("uploads/") :]

    directory = posixpath.dirname(original)
    source_filename = filename or posixpath.basename(original)
    safe_base, safe_ext = _split_filename(source_filename)
    derivative = _safe_slug(derivative_kind, "preview")
    unique_name = f"{uuid.uuid4().hex}_{safe_base}{safe_ext}"
    if directory:
        return f"uploads/_derived/{directory}/{derivative}/{unique_name}"
    return f"uploads/_derived/{derivative}/{unique_name}"


def build_deterministic_derived_upload_path(
    original_upload_path: str,
    derivative_kind: str,
    *,
    filename: str | None = None,
    extension: str | None = None,
) -> str:
    original = (original_upload_path or "").lstrip("/")
    if original.startswith("uploads/"):
        original = original[len("uploads/") :]

    directory = posixpath.dirname(original)
    source_filename = filename or posixpath.basename(original)
    safe_base, safe_ext = _split_filename(source_filename)
    derivative = _safe_slug(derivative_kind, "preview")
    final_ext = safe_ext
    if extension:
        normalized_ext = extension.lower()
        if not normalized_ext.startswith("."):
            normalized_ext = f".{normalized_ext}"
        final_ext = normalized_ext
    deterministic_name = f"{safe_base}{final_ext}"
    if directory:
        return f"uploads/_derived/{directory}/{derivative}/{deterministic_name}"
    return f"uploads/_derived/{derivative}/{deterministic_name}"
