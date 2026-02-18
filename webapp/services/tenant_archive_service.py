from collections.abc import Iterable

from django.utils import timezone

from webapp.models import LeaseAgreement, Tenant


def _normalize_tenant_ids(tenant_ids: Iterable[int]) -> list[int]:
    normalized_ids: set[int] = set()
    for tenant_id in tenant_ids:
        if tenant_id is None:
            continue
        normalized_ids.add(int(tenant_id))
    return sorted(normalized_ids)


def sync_tenant_archive_state(*, tenant_ids: Iterable[int]) -> None:
    normalized_ids = _normalize_tenant_ids(tenant_ids)
    if not normalized_ids:
        return

    active_tenant_ids = set(
        Tenant.objects.filter(
            pk__in=normalized_ids,
            leases__status=LeaseAgreement.Status.AKTIV,
        )
        .values_list("pk", flat=True)
        .distinct()
    )
    archive_tenant_ids = set(normalized_ids) - active_tenant_ids
    now = timezone.now()

    if archive_tenant_ids:
        Tenant.objects.filter(
            pk__in=archive_tenant_ids,
            is_archived=False,
        ).update(
            is_archived=True,
            archived_at=now,
        )
        Tenant.objects.filter(
            pk__in=archive_tenant_ids,
            is_archived=True,
            archived_at__isnull=True,
        ).update(archived_at=now)

    if active_tenant_ids:
        Tenant.objects.filter(
            pk__in=active_tenant_ids,
            is_archived=True,
        ).update(
            is_archived=False,
            archived_at=None,
        )
