from django.db import transaction
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from webapp.models import LeaseAgreement
from webapp.services.tenant_archive_service import sync_tenant_archive_state

_CLEARED_TENANT_IDS_ATTR = "_tenant_ids_before_clear"


def _schedule_archive_sync(*, tenant_ids) -> None:
    normalized_ids = sorted({int(tenant_id) for tenant_id in tenant_ids if tenant_id is not None})
    if not normalized_ids:
        return
    transaction.on_commit(lambda: sync_tenant_archive_state(tenant_ids=normalized_ids))


@receiver(post_save, sender=LeaseAgreement)
def lease_post_save_sync_tenants(sender, instance, **kwargs):
    _schedule_archive_sync(tenant_ids=instance.tenants.values_list("pk", flat=True))


@receiver(m2m_changed, sender=LeaseAgreement.tenants.through)
def lease_tenants_changed_sync_archive(sender, instance, action, reverse, pk_set, **kwargs):
    if reverse:
        if action in {"post_add", "post_remove", "post_clear"}:
            _schedule_archive_sync(tenant_ids=[instance.pk])
        return

    if action == "pre_clear":
        setattr(
            instance,
            _CLEARED_TENANT_IDS_ATTR,
            list(instance.tenants.values_list("pk", flat=True)),
        )
        return

    if action in {"post_add", "post_remove"}:
        _schedule_archive_sync(tenant_ids=pk_set or [])
        return

    if action == "post_clear":
        _schedule_archive_sync(tenant_ids=getattr(instance, _CLEARED_TENANT_IDS_ATTR, []))
        if hasattr(instance, _CLEARED_TENANT_IDS_ATTR):
            delattr(instance, _CLEARED_TENANT_IDS_ATTR)
