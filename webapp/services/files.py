import mimetypes
import os
from dataclasses import dataclass
from typing import Any

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from webapp.models import Datei, DateiOperationLog, DateiZuordnung


ALLOWED_MIME_BY_EXTENSION = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
}

DEFAULT_MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024

MAX_FILE_SIZE_BY_CATEGORY = {
    Datei.Kategorie.ZAEHLERFOTO: 5 * 1024 * 1024,
    Datei.Kategorie.BILD: 10 * 1024 * 1024,
    Datei.Kategorie.DOKUMENT: 15 * 1024 * 1024,
    Datei.Kategorie.RECHNUNG: 15 * 1024 * 1024,
    Datei.Kategorie.BRIEF: 15 * 1024 * 1024,
    Datei.Kategorie.VERTRAG: 20 * 1024 * 1024,
    Datei.Kategorie.SONSTIGES: 10 * 1024 * 1024,
}

ALLOWED_TARGET_MODELS = {
    "property",
    "unit",
    "tenant",
    "leaseagreement",
    "meter",
    "meterreading",
    "betriebskostenbeleg",
}

ATTACHMENT_FILTER_DEFINITIONS = (
    ("alle", "Alle"),
    ("bilder", "Bilder"),
    ("dokumente", "Dokumente"),
    ("briefe", "Briefe"),
    ("zaehlerfotos", "Zählerfotos"),
)

ATTACHMENT_FILTER_CATEGORIES = {
    "alle": None,
    "bilder": (Datei.Kategorie.BILD,),
    "dokumente": (
        Datei.Kategorie.DOKUMENT,
        Datei.Kategorie.RECHNUNG,
        Datei.Kategorie.VERTRAG,
    ),
    "briefe": (Datei.Kategorie.BRIEF,),
    "zaehlerfotos": (Datei.Kategorie.ZAEHLERFOTO,),
}


@dataclass(frozen=True)
class DateiValidationResult:
    original_name: str
    extension: str
    mime_type: str
    size_bytes: int
    max_size_bytes: int


class DateiService:
    GENERATED_LETTER_DESCRIPTIONS = (
        "BK-Abrechnung ",
        "VPI-Anpassung ",
    )

    @classmethod
    def normalize_filter_key(cls, filter_key: str | None) -> str:
        key = (filter_key or "alle").strip().lower()
        if key not in ATTACHMENT_FILTER_CATEGORIES:
            return "alle"
        return key

    @classmethod
    def filter_definitions(cls):
        return [
            {"key": key, "label": label}
            for key, label in ATTACHMENT_FILTER_DEFINITIONS
        ]

    @classmethod
    def category_choices(cls):
        return list(Datei.Kategorie.choices)

    @classmethod
    def resolve_upload_category(
        cls,
        *,
        provided_category: str | None,
        uploaded_file,
        target_object: Any | None = None,
    ) -> str:
        valid_categories = {value for value, _label in Datei.Kategorie.choices}
        normalized = str(provided_category or "").strip().lower()
        if normalized:
            if normalized in valid_categories:
                return normalized
            raise ValidationError("Bitte eine gültige Dateikategorie auswählen.")
        return cls.infer_upload_category(uploaded_file=uploaded_file, target_object=target_object)

    @classmethod
    def infer_upload_category(cls, *, uploaded_file, target_object: Any | None = None) -> str:
        target_model = (
            str(getattr(getattr(target_object, "_meta", None), "model_name", "") or "")
            .strip()
            .lower()
        )
        file_name = os.path.basename(getattr(uploaded_file, "name", "") or "")
        _, extension = os.path.splitext(file_name)
        extension = extension.lower()
        mime_type = str(getattr(uploaded_file, "content_type", "") or "").strip().lower()
        is_image = extension in {".jpg", ".jpeg", ".png"} or mime_type.startswith("image/")

        if target_model == "betriebskostenbeleg":
            return Datei.Kategorie.RECHNUNG
        if target_model == "meterreading" and is_image:
            return Datei.Kategorie.ZAEHLERFOTO
        if is_image:
            return Datei.Kategorie.BILD
        if extension == ".pdf" or mime_type == "application/pdf":
            return Datei.Kategorie.DOKUMENT
        return Datei.Kategorie.SONSTIGES

    @classmethod
    def effective_mime_type(cls, *, datei: Datei) -> str:
        mime_type = str(datei.mime_type or "").strip().lower()
        if mime_type and mime_type != "application/octet-stream":
            return mime_type

        candidate_names = [
            str(datei.original_name or "").strip(),
            os.path.basename(str(getattr(datei.file, "name", "") or "").strip()),
        ]
        for candidate in candidate_names:
            if not candidate:
                continue
            guessed_type = mimetypes.guess_type(candidate)[0]
            if guessed_type:
                return guessed_type.lower()

        if mime_type:
            return mime_type
        return "application/octet-stream"

    @classmethod
    def is_image_file(cls, *, datei: Datei) -> bool:
        mime_type = cls.effective_mime_type(datei=datei)
        if mime_type.startswith("image/"):
            return True

        candidate_name = str(datei.original_name or "").strip() or os.path.basename(
            str(getattr(datei.file, "name", "") or "").strip()
        )
        _base, extension = os.path.splitext(candidate_name)
        extension = extension.lower()
        if extension in {".jpg", ".jpeg", ".png"}:
            return True

        if not extension and datei.kategorie in {
            Datei.Kategorie.BILD,
            Datei.Kategorie.ZAEHLERFOTO,
        }:
            return True

        return False

    @classmethod
    def image_mime_type(cls, *, datei: Datei) -> str:
        mime_type = cls.effective_mime_type(datei=datei)
        if mime_type.startswith("image/"):
            return mime_type

        candidate_name = str(datei.original_name or "").strip() or os.path.basename(
            str(getattr(datei.file, "name", "") or "").strip()
        )
        _base, extension = os.path.splitext(candidate_name)
        extension = extension.lower()
        if extension in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if extension == ".png":
            return "image/png"

        if datei.kategorie in {Datei.Kategorie.BILD, Datei.Kategorie.ZAEHLERFOTO}:
            return "image/jpeg"

        return mime_type

    @classmethod
    def list_assignments_for_object(
        cls,
        *,
        target_object,
        filter_key: str = "alle",
        include_archived: bool = False,
    ):
        content_type = ContentType.objects.get_for_model(target_object)
        normalized_filter = cls.normalize_filter_key(filter_key)
        categories = ATTACHMENT_FILTER_CATEGORIES.get(normalized_filter)

        queryset = (
            DateiZuordnung.objects.filter(
                content_type=content_type,
                object_id=target_object.pk,
            )
            .select_related("datei")
            .order_by("-datei__created_at", "-id")
        )
        if not include_archived:
            queryset = queryset.filter(datei__is_archived=False)
        if categories:
            queryset = queryset.filter(datei__kategorie__in=categories)
        return list(queryset)

    @classmethod
    def resolve_target_object(
        cls,
        *,
        app_label: str,
        model_name: str,
        object_id: int,
    ) -> Any:
        if not app_label or not model_name:
            raise ValidationError("Bitte ein gültiges Zielobjekt angeben.")

        model_label = str(model_name).strip().lower()
        if model_label not in ALLOWED_TARGET_MODELS:
            raise ValidationError("Dieser Objekttyp darf nicht mit Dateien verknüpft werden.")

        try:
            model_class = apps.get_model(app_label=app_label, model_name=model_label)
        except LookupError as exc:
            raise ValidationError("Unbekanntes Zielobjekt.") from exc
        if model_class is None:
            raise ValidationError("Unbekanntes Zielobjekt.")

        target_object = model_class.objects.filter(pk=object_id).first()
        if target_object is None:
            raise ValidationError("Das Zielobjekt wurde nicht gefunden.")
        return target_object

    @classmethod
    def validate_upload(
        cls,
        *,
        uploaded_file,
        kategorie: str,
    ) -> DateiValidationResult:
        if uploaded_file is None:
            raise ValidationError("Bitte eine Datei auswählen.")

        original_name = os.path.basename(getattr(uploaded_file, "name", "") or "")
        cls._validate_filename(original_name)

        _, extension = os.path.splitext(original_name)
        extension = extension.lower()
        if extension not in ALLOWED_MIME_BY_EXTENSION:
            raise ValidationError("Dateityp nicht erlaubt. Erlaubt sind PDF, JPG, JPEG und PNG.")

        allowed_mimes = ALLOWED_MIME_BY_EXTENSION[extension]
        mime_type = (getattr(uploaded_file, "content_type", "") or "").lower().strip()
        if mime_type and mime_type not in allowed_mimes:
            raise ValidationError("MIME-Typ und Dateiendung passen nicht zusammen.")
        if not mime_type:
            mime_type = sorted(allowed_mimes)[0]

        size_bytes = int(getattr(uploaded_file, "size", 0) or 0)
        max_size_bytes = int(
            MAX_FILE_SIZE_BY_CATEGORY.get(kategorie, DEFAULT_MAX_FILE_SIZE_BYTES)
        )
        if size_bytes <= 0:
            raise ValidationError("Die Datei ist leer.")
        if size_bytes > max_size_bytes:
            limit_mb = max_size_bytes / (1024 * 1024)
            raise ValidationError(
                f"Datei ist zu groß. Maximal erlaubt für diese Kategorie: {limit_mb:.0f} MB."
            )

        return DateiValidationResult(
            original_name=original_name,
            extension=extension,
            mime_type=mime_type,
            size_bytes=size_bytes,
            max_size_bytes=max_size_bytes,
        )

    @classmethod
    def can_upload(cls, *, target_object: Any, user=None) -> bool:
        return True

    @classmethod
    def can_download(cls, *, user, datei: Datei) -> bool:
        return not bool(datei.is_archived)

    @classmethod
    def can_delete(cls, *, user, datei: Datei) -> bool:
        return True

    @classmethod
    def can_archive(cls, *, user, datei: Datei) -> bool:
        return True

    @classmethod
    def can_restore(cls, *, user, datei: Datei) -> bool:
        return True

    @classmethod
    def assert_can_upload(cls, *, target_object: Any, user=None):
        if not cls.can_upload(target_object=target_object, user=user):
            raise PermissionDenied("Datei-Upload ist derzeit nicht verfügbar.")

    @classmethod
    def assert_can_download(cls, *, user, datei: Datei):
        if not cls.can_download(user=user, datei=datei):
            raise PermissionDenied("Archivierte Dateien können nicht geöffnet werden.")

    @classmethod
    def assert_can_delete(cls, *, user, datei: Datei):
        if not cls.can_delete(user=user, datei=datei):
            raise PermissionDenied("Datei kann derzeit nicht gelöscht werden.")

    @classmethod
    def assert_can_archive(cls, *, user, datei: Datei):
        if not cls.can_archive(user=user, datei=datei):
            raise PermissionDenied("Datei kann derzeit nicht archiviert werden.")

    @classmethod
    def assert_can_restore(cls, *, user, datei: Datei):
        if not cls.can_restore(user=user, datei=datei):
            raise PermissionDenied("Datei kann derzeit nicht wiederhergestellt werden.")

    @classmethod
    def upload(
        cls,
        *,
        user=None,
        uploaded_file,
        kategorie: str | None = None,
        target_object: Any,
        beschreibung: str = "",
    ) -> Datei:
        try:
            cls.assert_can_upload(target_object=target_object, user=user)
            resolved_kategorie = cls.resolve_upload_category(
                provided_category=kategorie,
                uploaded_file=uploaded_file,
                target_object=target_object,
            )
            cls.validate_upload(uploaded_file=uploaded_file, kategorie=resolved_kategorie)
        except (ValidationError, PermissionDenied) as exc:
            cls.log_operation(
                operation=DateiOperationLog.Operation.UPLOAD,
                actor=None,
                content_object=target_object,
                success=False,
                detail=str(exc),
            )
            raise

        with transaction.atomic():
            datei = Datei(
                file=uploaded_file,
                kategorie=resolved_kategorie,
                beschreibung=(beschreibung or "").strip(),
                uploaded_by=None,
            )
            datei.set_upload_context(content_object=target_object)
            datei.full_clean()
            datei.save()

            DateiZuordnung.objects.create(
                datei=datei,
                content_type=ContentType.objects.get_for_model(target_object),
                object_id=target_object.pk,
                created_by=None,
            )

            cls.log_operation(
                operation=DateiOperationLog.Operation.UPLOAD,
                actor=None,
                datei=datei,
                content_object=target_object,
                success=True,
                detail="Upload erfolgreich.",
            )
            return datei

    @classmethod
    def prepare_download(cls, *, user, datei: Datei) -> Datei:
        content_object = cls._primary_content_object(datei)
        try:
            cls.assert_can_download(user=user, datei=datei)
        except PermissionDenied as exc:
            cls.log_operation(
                operation=DateiOperationLog.Operation.VIEW,
                actor=user,
                datei=datei,
                content_object=content_object,
                success=False,
                detail=str(exc),
            )
            raise

        cls.log_operation(
            operation=DateiOperationLog.Operation.VIEW,
            actor=user,
            datei=datei,
            content_object=content_object,
            success=True,
            detail="Download freigegeben.",
        )
        return datei

    @classmethod
    def replacement_for_archived_download(cls, *, datei: Datei) -> Datei | None:
        if not datei.is_archived:
            return None

        beschreibung = (datei.beschreibung or "").strip()
        if not beschreibung.startswith(cls.GENERATED_LETTER_DESCRIPTIONS):
            return None

        primary_assignment = (
            datei.zuordnungen.order_by("id")
            .values("content_type_id", "object_id")
            .first()
        )
        if primary_assignment is None:
            return None

        replacement_assignment = (
            DateiZuordnung.objects.filter(
                content_type_id=primary_assignment["content_type_id"],
                object_id=primary_assignment["object_id"],
                datei__is_archived=False,
                datei__original_name=datei.original_name,
                datei__kategorie=datei.kategorie,
                datei__beschreibung=datei.beschreibung,
            )
            .exclude(datei_id=datei.pk)
            .order_by("-datei__created_at", "-datei_id")
            .first()
        )
        if replacement_assignment is None:
            return None

        return replacement_assignment.datei

    @classmethod
    def archive(cls, *, user, datei: Datei) -> Datei:
        content_object = cls._primary_content_object(datei)
        try:
            cls.assert_can_archive(user=user, datei=datei)
        except PermissionDenied as exc:
            cls.log_operation(
                operation=DateiOperationLog.Operation.DELETE,
                actor=user,
                datei=datei,
                content_object=content_object,
                success=False,
                detail=str(exc),
            )
            raise

        if datei.is_archived:
            return datei

        datei.is_archived = True
        datei.archived_at = timezone.now()
        datei.archived_by = None
        datei.save(update_fields=["is_archived", "archived_at", "archived_by"])

        file_name = datei.original_name or os.path.basename(datei.file.name or "")
        cls.log_operation(
            operation=DateiOperationLog.Operation.DELETE,
            actor=user,
            datei=datei,
            content_object=content_object,
            success=True,
            detail=f"Datei archiviert: {file_name}",
        )
        return datei

    @classmethod
    def restore(cls, *, user, datei: Datei) -> Datei:
        content_object = cls._primary_content_object(datei)
        try:
            cls.assert_can_restore(user=user, datei=datei)
        except PermissionDenied as exc:
            cls.log_operation(
                operation=DateiOperationLog.Operation.DELETE,
                actor=user,
                datei=datei,
                content_object=content_object,
                success=False,
                detail=str(exc),
            )
            raise

        if not datei.is_archived:
            return datei

        datei.is_archived = False
        datei.archived_at = None
        datei.archived_by = None
        datei.save(update_fields=["is_archived", "archived_at", "archived_by"])

        file_name = datei.original_name or os.path.basename(datei.file.name or "")
        cls.log_operation(
            operation=DateiOperationLog.Operation.DELETE,
            actor=user,
            datei=datei,
            content_object=content_object,
            success=True,
            detail=f"Datei wiederhergestellt: {file_name}",
        )
        return datei

    @classmethod
    def delete(cls, *, user, datei: Datei):
        content_object = cls._primary_content_object(datei)
        try:
            cls.assert_can_delete(user=user, datei=datei)
        except PermissionDenied as exc:
            cls.log_operation(
                operation=DateiOperationLog.Operation.DELETE,
                actor=user,
                datei=datei,
                content_object=content_object,
                success=False,
                detail=str(exc),
            )
            raise

        file_name = datei.original_name or os.path.basename(datei.file.name or "")
        cls.log_operation(
            operation=DateiOperationLog.Operation.DELETE,
            actor=user,
            datei=datei,
            content_object=content_object,
            success=True,
            detail=f"Datei gelöscht: {file_name}",
        )

        if datei.file:
            datei.file.delete(save=False)
        datei.delete()

    @classmethod
    def log_operation(
        cls,
        *,
        operation: str,
        actor,
        datei: Datei | None = None,
        content_object: Any | None = None,
        success: bool = True,
        detail: str = "",
    ) -> DateiOperationLog:
        content_type = None
        object_id = None
        if content_object is not None and getattr(content_object, "pk", None) is not None:
            content_type = ContentType.objects.get_for_model(content_object)
            object_id = content_object.pk

        file_name = ""
        if datei is not None:
            file_name = datei.original_name or os.path.basename(datei.file.name or "")

        return DateiOperationLog.objects.create(
            operation=operation,
            success=bool(success),
            actor=None,
            datei=datei,
            datei_name=file_name,
            content_type=content_type,
            object_id=object_id,
            detail=(detail or "")[:500],
        )

    @staticmethod
    def _validate_filename(filename: str):
        if not filename:
            raise ValidationError("Ungültiger Dateiname.")

        if filename != os.path.basename(filename):
            raise ValidationError("Ungültiger Dateiname.")

        if any(token in filename for token in ("..", "/", "\\", "\x00")):
            raise ValidationError("Dateiname enthält unzulässige Zeichen.")

        if filename.startswith(".") or filename.endswith("."):
            raise ValidationError("Dateiname ist nicht zulässig.")

    @staticmethod
    def _primary_content_object(datei: Datei):
        zuordnung = (
            datei.zuordnungen.select_related("content_type")
            .order_by("id")
            .first()
        )
        if zuordnung is None:
            return None
        return zuordnung.content_object
