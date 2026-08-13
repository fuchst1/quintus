"""Safe, Paperless-independent reset of derived bookkeeping workflow data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.db.models import Count, Q
from django.utils import timezone

from .choices import CATEGORY_CHOICES
from .models import (
    BankStatement,
    BankTransaction,
    BookingEntry,
    MatchingRule,
    ManualInvoice,
    ManualInvoiceEntry,
    MatchingRuleBookingTemplate,
    SupportingDocument,
)


@dataclass(frozen=True)
class WorkflowResetSelection:
    """The source querysets used by both dry-run reporting and execution."""

    bank_transactions: Any
    manual_invoices: Any


@dataclass(frozen=True)
class WorkflowResetReport:
    """Counts and warnings calculated from one reset selection."""

    kept: dict[str, int]
    reset: dict[str, int]
    deleted: dict[str, int]
    warnings: tuple[str, ...]
    details: dict[str, Any]


def build_reset_selection(using=DEFAULT_DB_ALIAS) -> WorkflowResetSelection:
    """Return the complete, stable source selection for a workflow reset."""
    return WorkflowResetSelection(
        bank_transactions=BankTransaction.objects.using(using).all(),
        manual_invoices=ManualInvoice.objects.using(using).all(),
    )


def _positive_paperless_count(queryset):
    return queryset.filter(paperless_document_id__gt=0).count()


def _stable_uuid_count(using):
    return sum(
        model.objects.using(using).filter(reference_uuid__isnull=False).count()
        for model in (BankStatement, ManualInvoice, SupportingDocument)
    )


def _status_counts(queryset):
    return dict(
        queryset.values("status")
        .annotate(count=Count("id"))
        .values_list("status", "count")
    )


def collect_reset_report(
    selection: WorkflowResetSelection,
    *,
    using=DEFAULT_DB_ALIAS,
) -> WorkflowResetReport:
    """Collect all dry-run values without loading complete source tables."""
    bank_transactions = selection.bank_transactions
    manual_invoices = selection.manual_invoices
    bank_entries = BookingEntry.objects.using(using).filter(
        bank_transaction__in=bank_transactions
    )
    manual_entries = ManualInvoiceEntry.objects.using(using).filter(
        manual_invoice__in=manual_invoices
    )
    bank_status_counts = _status_counts(bank_transactions)
    manual_status_counts = _status_counts(manual_invoices)
    booking_draft_sources = (
        bank_entries.values("bank_transaction_id").distinct().count()
        + manual_entries.values("manual_invoice_id").distinct().count()
    )
    booking_rows = bank_entries.count() + manual_entries.count()
    deleted = {
        "BookingEntry": bank_entries.count(),
        "ManualInvoiceEntry": manual_entries.count(),
    }
    manually_edited_rows = (
        bank_entries.filter(matching_rule_template__isnull=True).count()
        + manual_entries.count()
    )
    ready_count = (
        bank_transactions.filter(
            status__in=(
                BankTransaction.Status.REVIEWED,
                BankTransaction.Status.BOOKED,
            )
        ).count()
        + manual_invoices.filter(status=ManualInvoice.Status.READY).count()
    )
    booked_count = bank_transactions.filter(
        status=BankTransaction.Status.BOOKED
    ).count()
    exported_count = 0  # bookkeeping has no persisted export-run model/status.

    orphan_supporting_documents = SupportingDocument.objects.using(using).filter(
        Q(matching_rule__isnull=True, bank_transaction__isnull=True)
        | Q(matching_rule__isnull=False, bank_transaction__isnull=False)
    ).count()
    missing_uuid_count = sum(
        model.objects.using(using).filter(reference_uuid__isnull=True).count()
        for model in (BankStatement, ManualInvoice, SupportingDocument)
    )
    paperless_link_count = (
        _positive_paperless_count(
            BankStatement.objects.using(using)
        )
        + _positive_paperless_count(manual_invoices)
        + _positive_paperless_count(SupportingDocument.objects.using(using))
    )
    original_file_count = (
        BankStatement.objects.using(using)
        .exclude(temporary_pdf="")
        .filter(temporary_pdf__isnull=False)
        .count()
        + manual_invoices.exclude(temporary_pdf="")
        .filter(temporary_pdf__isnull=False)
        .count()
        + SupportingDocument.objects.using(using)
        .exclude(temporary_file="")
        .filter(temporary_file__isnull=False)
        .count()
    )

    warnings = []
    if booked_count:
        warnings.append(f"{booked_count} gebuchte Vorgänge blockieren den Reset.")
    if exported_count:
        warnings.append(
            f"{exported_count} exportierte Vorgänge blockieren den Reset."
        )
    if manually_edited_rows:
        warnings.append(
            f"{manually_edited_rows} manuell erkennbare Buchungszeile(n) werden entfernt."
        )
    if paperless_link_count:
        warnings.append(
            f"{paperless_link_count} Paperless-Verknüpfung(en) bleiben unverändert erhalten."
        )
    if missing_uuid_count:
        warnings.append(
            f"{missing_uuid_count} Datensatz/Datensätze haben keine stabile UUID."
        )
    if orphan_supporting_documents:
        warnings.append(
            f"{orphan_supporting_documents} SupportingDocument-Beziehung(en) sind unklar."
        )

    kept = {
        "Matching-Regeln": MatchingRule.objects.using(using).count(),
        "Regelversionen": MatchingRule.objects.using(using).count(),
        "Regel-Ergebniszeilen": MatchingRuleBookingTemplate.objects.using(using).count(),
        "Kategorien": len(CATEGORY_CHOICES),
        "Stammdatensätze": 0,
        "Kontoauszüge": BankStatement.objects.using(using).count(),
        "Banktransaktionen": bank_transactions.count(),
        "manuelle Belege": manual_invoices.count(),
        "Paperless-Verknüpfungen": paperless_link_count,
        "stabile Bookkeeping-UUIDs": _stable_uuid_count(using),
        "Originaldateien/Upload-Verweise": original_file_count,
        "Import-Hashes": bank_transactions.exclude(source_hash="").count(),
    }
    reset = {
        "Banktransaktionen": sum(bank_status_counts.values()),
        "Matching-Zuordnungen": bank_transactions.filter(
            matched_rule__isnull=False
        ).count(),
        "Buchungsentwürfe": booking_draft_sources,
        "Buchungszeilen": booking_rows,
        "manuell bearbeitete Buchungszeilen": manually_edited_rows,
        "buchungsfertige Vorgänge": ready_count,
        "gebuchte Vorgänge": booked_count,
        "exportierte Vorgänge": exported_count,
        "manuelle Belege auf Entwurf": manual_invoices.exclude(
            status=ManualInvoice.Status.DRAFT
        ).count(),
        "Export-/Übergabeverknüpfungen": exported_count,
    }
    return WorkflowResetReport(
        kept=kept,
        reset=reset,
        deleted=deleted,
        warnings=tuple(warnings),
        details={
            "bank_status_counts": bank_status_counts,
            "manual_invoice_status_counts": manual_status_counts,
            "booked_count": booked_count,
            "exported_count": exported_count,
            "orphan_supporting_documents": orphan_supporting_documents,
            "missing_uuid_count": missing_uuid_count,
            "paperless_link_count": paperless_link_count,
        },
    )


def execute_workflow_reset(
    selection: WorkflowResetSelection,
    *,
    using=DEFAULT_DB_ALIAS,
) -> WorkflowResetReport:
    """Delete only derived booking rows and restore source workflow states."""
    before = collect_reset_report(selection, using=using)
    with transaction.atomic(using=using):
        bank_transactions = selection.bank_transactions.select_for_update()
        manual_invoices = selection.manual_invoices.select_for_update()
        deleted_bank, _ = BookingEntry.objects.using(using).filter(
            bank_transaction__in=bank_transactions
        ).delete()
        deleted_manual, _ = ManualInvoiceEntry.objects.using(using).filter(
            manual_invoice__in=manual_invoices
        ).delete()

        bank_transactions.filter(
            Q(status__isnull=False) & ~Q(status=BankTransaction.Status.IMPORTED)
            | Q(matched_rule__isnull=False)
        ).update(
            matched_rule=None,
            status=BankTransaction.Status.IMPORTED,
        )
        manual_invoices.exclude(status=ManualInvoice.Status.DRAFT).update(
            status=ManualInvoice.Status.DRAFT,
            updated_at=timezone.now(),
        )
        _assert_reset_state(selection, before, using=using)

    deleted = {
        "BookingEntry": deleted_bank,
        "ManualInvoiceEntry": deleted_manual,
    }
    return WorkflowResetReport(
        kept=before.kept,
        reset=before.reset,
        deleted=deleted,
        warnings=before.warnings,
        details=before.details,
    )


def _assert_reset_state(
    selection: WorkflowResetSelection,
    before: WorkflowResetReport,
    *,
    using=DEFAULT_DB_ALIAS,
) -> None:
    """Fail inside the transaction if any source or derived state is unexpected."""
    bank_transactions = selection.bank_transactions
    manual_invoices = selection.manual_invoices
    if bank_transactions.filter(matched_rule__isnull=False).exists():
        raise RuntimeError("Nach dem Reset besteht noch eine Matching-Zuordnung.")
    if bank_transactions.exclude(status=BankTransaction.Status.IMPORTED).exists():
        raise RuntimeError("Nach dem Reset befindet sich eine Banktransaktion nicht im Importstatus.")
    if manual_invoices.exclude(status=ManualInvoice.Status.DRAFT).exists():
        raise RuntimeError("Nach dem Reset befindet sich ein manueller Beleg nicht im Entwurfsstatus.")
    if BookingEntry.objects.using(using).filter(
        bank_transaction__in=bank_transactions
    ).exists():
        raise RuntimeError("Nach dem Reset sind noch Bank-Buchungszeilen vorhanden.")
    if ManualInvoiceEntry.objects.using(using).filter(
        manual_invoice__in=manual_invoices
    ).exists():
        raise RuntimeError("Nach dem Reset sind noch manuelle Buchungszeilen vorhanden.")

    after = collect_reset_report(selection, using=using)
    if after.kept != before.kept:
        raise RuntimeError("Geschützte Quelldaten haben sich beim Reset verändert.")


def database_path(using=DEFAULT_DB_ALIAS) -> Path | None:
    """Return the configured SQLite path, or ``None`` for other databases."""
    connection = connections[using]
    if connection.vendor != "sqlite":
        return None
    name = connection.settings_dict.get("NAME")
    if not name or str(name) == ":memory:" or str(name).startswith("file:"):
        return None
    return Path(name).expanduser().resolve(strict=False)
