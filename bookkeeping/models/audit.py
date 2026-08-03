import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .master_data import Mandant


class AuditEreignis(models.Model):
    mandant = models.ForeignKey(Mandant, on_delete=models.PROTECT, related_name="audit_ereignisse")
    objekt_typ = models.CharField(max_length=100, verbose_name=_("Objekttyp"))
    objekt_id = models.CharField(max_length=100, verbose_name=_("Objekt-ID"))
    aktion = models.CharField(max_length=100, verbose_name=_("Aktion"))
    vorher = models.JSONField(default=dict, blank=True, verbose_name=_("Vorher"))
    nachher = models.JSONField(default=dict, blank=True, verbose_name=_("Nachher"))
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookkeeping_audit_ereignisse",
        verbose_name=_("Benutzer"),
    )
    zeitpunkt = models.DateTimeField(auto_now_add=True, verbose_name=_("Zeitpunkt"))
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)

    class Meta:
        verbose_name = _("Audit-Ereignis")
        verbose_name_plural = _("Audit-Ereignisse")
        ordering = ["-zeitpunkt", "-id"]
        indexes = [models.Index(fields=["objekt_typ", "objekt_id"], name="bk_audit_object_idx")]

    def __str__(self) -> str:
        return f"{self.aktion} · {self.objekt_typ} #{self.objekt_id}"
