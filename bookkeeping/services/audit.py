from typing import Any

from django.contrib.auth.models import AnonymousUser

from bookkeeping.models import AuditEreignis, Mandant


def record_audit_event(
    *,
    mandant: Mandant,
    objekt_typ: str,
    objekt_id: int | str,
    aktion: str,
    vorher: dict[str, Any] | None = None,
    nachher: dict[str, Any] | None = None,
    user: Any = None,
) -> AuditEreignis:
    """Store a local audit record without imposing Django authentication."""
    actor = None if user is None or isinstance(user, AnonymousUser) or not user.is_authenticated else user
    return AuditEreignis.objects.create(
        mandant=mandant,
        objekt_typ=objekt_typ,
        objekt_id=str(objekt_id),
        aktion=aktion,
        vorher=vorher or {},
        nachher=nachher or {},
        benutzer=actor,
    )
