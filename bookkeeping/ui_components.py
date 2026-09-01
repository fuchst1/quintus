"""Shared presentation data for the Core Ledger component system."""

from dataclasses import dataclass

from django.db import models
from django.urls import reverse
from django.views.generic import TemplateView

from .models import BankStatement, BankTransaction, ManualInvoice, SupportingDocument


@dataclass(frozen=True, slots=True)
class StatusPresentation:
    """The user-facing presentation of one model status."""

    label: str
    variant: str
    icon: str
    known: bool = True


STATUS_FAMILIES: dict[str, type[models.TextChoices]] = {
    "bank_transaction": BankTransaction.Status,
    "manual_invoice": ManualInvoice.Status,
    "manual_invoice_paperless": ManualInvoice.PaperlessStatus,
    "manual_invoice_ai": ManualInvoice.AIStatus,
    "bank_statement_paperless": BankStatement.PaperlessStatus,
    "supporting_document_transfer": SupportingDocument.TransferStatus,
}


_STATUS_VARIANTS: dict[str, dict[str, str]] = {
    "bank_transaction": {
        BankTransaction.Status.IMPORTED: "info",
        BankTransaction.Status.MATCHED: "info",
        BankTransaction.Status.REVIEWED: "success",
        BankTransaction.Status.BOOKED: "success",
    },
    "manual_invoice": {
        ManualInvoice.Status.DRAFT: "neutral",
        ManualInvoice.Status.READY: "success",
    },
    "manual_invoice_paperless": {
        ManualInvoice.PaperlessStatus.NOT_STARTED: "neutral",
        ManualInvoice.PaperlessStatus.PENDING: "info",
        ManualInvoice.PaperlessStatus.COMPLETED: "success",
        ManualInvoice.PaperlessStatus.FAILED: "error",
        ManualInvoice.PaperlessStatus.DELETED: "neutral",
    },
    "manual_invoice_ai": {
        ManualInvoice.AIStatus.NOT_STARTED: "neutral",
        ManualInvoice.AIStatus.COMPLETED: "success",
        ManualInvoice.AIStatus.FAILED: "error",
    },
    "bank_statement_paperless": {
        BankStatement.PaperlessStatus.PENDING: "info",
        BankStatement.PaperlessStatus.COMPLETED: "success",
        BankStatement.PaperlessStatus.DUPLICATE: "success",
        BankStatement.PaperlessStatus.METADATA_INCOMPLETE: "warning",
        BankStatement.PaperlessStatus.FAILED: "error",
    },
    "supporting_document_transfer": {
        SupportingDocument.TransferStatus.PENDING: "info",
        SupportingDocument.TransferStatus.COMPLETED: "success",
        SupportingDocument.TransferStatus.FAILED: "error",
    },
}


STATUS_ICONS = {
    "neutral": "bi-circle",
    "info": "bi-info-circle",
    "success": "bi-check-circle",
    "warning": "bi-exclamation-triangle",
    "error": "bi-x-circle",
}


def _build_status_registry() -> dict[str, dict[str, StatusPresentation]]:
    registry: dict[str, dict[str, StatusPresentation]] = {}
    for family, choices in STATUS_FAMILIES.items():
        variants = _STATUS_VARIANTS[family]
        choice_values = {choice.value for choice in choices}
        if choice_values != set(variants):
            raise RuntimeError(f"Status mapping for {family!r} does not match its model choices.")
        registry[family] = {
            choice.value: StatusPresentation(
                label=str(choice.label),
                variant=variants[choice.value],
                icon=STATUS_ICONS[variants[choice.value]],
            )
            for choice in choices
        }
    return registry


STATUS_REGISTRY = _build_status_registry()

UNKNOWN_STATUS = StatusPresentation(
    label="Unbekannt",
    variant="neutral",
    icon="bi-question-circle",
    known=False,
)

STATUS_FAMILY_LABELS = {
    "bank_transaction": "Banktransaktionen",
    "manual_invoice": "Manuelle Belege",
    "manual_invoice_paperless": "Manuelle Belege – Paperless",
    "manual_invoice_ai": "Manuelle Belege – KI",
    "bank_statement_paperless": "Kontoauszüge – Paperless",
    "supporting_document_transfer": "Belegübertragung",
}


def resolve_status(family: str, value: object) -> StatusPresentation:
    """Resolve a family/value pair without leaking status styling into templates."""

    family_statuses = STATUS_REGISTRY.get(str(family))
    if family_statuses is None:
        return UNKNOWN_STATUS
    return family_statuses.get(str(value), UNKNOWN_STATUS)


class ComponentShowcaseView(TemplateView):
    """Render the directly routable, navigation-independent component reference."""

    template_name = "bookkeeping/new_ui/component_showcase.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["showcase_breadcrumbs"] = [
            {"label": "Buchhaltung", "url": reverse("bookkeeping_overview")},
            {"label": "Komponenten"},
        ]
        context["status_groups"] = tuple(
            {
                "family": family,
                "label": STATUS_FAMILY_LABELS[family],
                "statuses": tuple(
                    {
                        "family": family,
                        "value": choice.value,
                        "presentation": STATUS_REGISTRY[family][choice.value],
                    }
                    for choice in choices
                ),
            }
            for family, choices in STATUS_FAMILIES.items()
        )
        return context
