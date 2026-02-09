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
    Datei.Kategorie.BRIEF: 15 * 1024 * 1024,
    Datei.Kategorie.VERTRAG: 20 * 1024 * 1024,
    Datei.Kategorie.SONSTIGES: 10 * 1024 * 1024,
}

ROLE_VERWALTER = "verwalter"
ROLE_EIGENTUEMER = "eigentuemer"
ROLE_MIETER = "mieter"

ALLOWED_TARGET_MODELS = {
    "property",
    "unit",
    "tenant",
    "leaseagreement",
    "meter",
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
    "dokumente": (Datei.Kategorie.DOKUMENT, Datei.Kategorie.VERTRAG),
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
            .select_related("datei", "datei__uploaded_by")
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
        if not cls._is_authenticated(user):
            return False
        if cls._is_admin(user):
            return True
        if datei.is_archived:
            return False
        if datei.uploaded_by_id == getattr(user, "pk", None) and user.has_perm("webapp.view_datei"):
            return True

        role_names = cls._role_names_for_user(user)
        zuordnungen = list(
            datei.zuordnungen.select_related("content_type").order_by("id")
        )
        if not zuordnungen:
            return False

        for zuordnung in zuordnungen:
            target = zuordnung.content_object
            if target is None:
                continue
            object_view_perm = f"{target._meta.app_label}.view_{target._meta.model_name}"
            if not (user.has_perm(object_view_perm, target) or user.has_perm(object_view_perm)):
                continue
            if zuordnung.sichtbar_fuer_verwalter and ROLE_VERWALTER in role_names:
                return True
            if zuordnung.sichtbar_fuer_eigentuemer and ROLE_EIGENTUEMER in role_names:
                return True
            if zuordnung.sichtbar_fuer_mieter and ROLE_MIETER in role_names:
                return True
        return False

    @classmethod
    def can_delete(cls, *, user, datei: Datei) -> bool:
        if not cls._is_authenticated(user):
            return False
        if cls._is_admin(user):
            return True
        if datei.uploaded_by_id != getattr(user, "pk", None):
            return False
        if not user.has_perm("webapp.delete_datei"):
            return False

        zuordnungen = list(datei.zuordnungen.order_by("id"))
        if not zuordnungen:
            return True

        for zuordnung in zuordnungen:
            target = zuordnung.content_object
            if target is None:
                continue
            required_perm = f"{target._meta.app_label}.change_{target._meta.model_name}"
            if user.has_perm(required_perm, target) or user.has_perm(required_perm):
                return True
        return False

    @classmethod
    def can_archive(cls, *, user, datei: Datei) -> bool:
        return cls.can_delete(user=user, datei=datei)

    @classmethod
    def can_restore(cls, *, user, datei: Datei) -> bool:
        if not cls._is_authenticated(user):
            return False
        if cls._is_admin(user):
            return True
        return bool(
            datei.uploaded_by_id == getattr(user, "pk", None)
            and user.has_perm("webapp.change_datei")
        )

    @classmethod
    def assert_can_upload(cls, *, target_object: Any, user=None):
        if not cls.can_upload(target_object=target_object, user=user):
            raise PermissionDenied("Sie haben keine Berechtigung für diesen Datei-Upload.")

    @classmethod
    def assert_can_download(cls, *, user, datei: Datei):
        if not cls.can_download(user=user, datei=datei):
            raise PermissionDenied("Sie haben keine Berechtigung für diesen Dateizugriff.")

    @classmethod
    def assert_can_delete(cls, *, user, datei: Datei):
        if not cls.can_delete(user=user, datei=datei):
            raise PermissionDenied("Sie haben keine Berechtigung zum Löschen dieser Datei.")

    @classmethod
    def assert_can_archive(cls, *, user, datei: Datei):
        if not cls.can_archive(user=user, datei=datei):
            raise PermissionDenied("Sie haben keine Berechtigung zum Archivieren dieser Datei.")

    @classmethod
    def assert_can_restore(cls, *, user, datei: Datei):
        if not cls.can_restore(user=user, datei=datei):
            raise PermissionDenied("Sie haben keine Berechtigung zum Wiederherstellen dieser Datei.")

    @classmethod
    def upload(
        cls,
        *,
        user=None,
        uploaded_file,
        kategorie: str,
        target_object: Any,
        beschreibung: str = "",
        kontext: str = "",
        sichtbar_fuer_verwalter: bool = True,
        sichtbar_fuer_eigentuemer: bool = False,
        sichtbar_fuer_mieter: bool = False,
    ) -> Datei:
        try:
            cls.assert_can_upload(target_object=target_object, user=user)
            cls.validate_upload(uploaded_file=uploaded_file, kategorie=kategorie)
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
                kategorie=kategorie,
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
                kontext=(kontext or "").strip(),
                sichtbar_fuer_verwalter=bool(sichtbar_fuer_verwalter),
                sichtbar_fuer_eigentuemer=bool(sichtbar_fuer_eigentuemer),
                sichtbar_fuer_mieter=bool(sichtbar_fuer_mieter),
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
        datei.archived_by = user if cls._is_authenticated(user) else None
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
            actor=actor if cls._is_authenticated(actor) else None,
            datei=datei,
            datei_name=file_name,
            content_type=content_type,
            object_id=object_id,
            detail=(detail or "")[:500],
        )

    @staticmethod
    def _is_authenticated(user) -> bool:
        return bool(user and getattr(user, "is_authenticated", False))

    @staticmethod
    def _is_admin(user) -> bool:
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and (getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))
        )

    @staticmethod
    def _role_names_for_user(user) -> set[str]:
        if not user or not getattr(user, "is_authenticated", False):
            return set()
        role_names = {group.name.strip().lower() for group in user.groups.all()}
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            role_names.add(ROLE_VERWALTER)
        return role_names

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

        parts = filename.split(".")
        if len(parts) > 2:
            raise ValidationError("Doppelte Dateiendungen sind nicht erlaubt.")

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
