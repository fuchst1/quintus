from __future__ import annotations

from django.db import transaction as db_transaction

from .models import (
    BankTransaction,
    BookingEntry,
    ManualInvoice,
    ManualInvoiceEntry,
)


def reset_bank_transaction_booking(bank_transaction: BankTransaction) -> None:
    """Remove only entries and return the source transaction to its prior state."""
    with db_transaction.atomic():
        locked_transaction = BankTransaction.objects.select_for_update().get(
            pk=bank_transaction.pk
        )
        BookingEntry.objects.filter(bank_transaction=locked_transaction).delete()
        target_status = (
            BankTransaction.Status.MATCHED
            if locked_transaction.matched_rule_id
            else BankTransaction.Status.IMPORTED
        )
        if locked_transaction.status != target_status:
            locked_transaction.status = target_status
            locked_transaction.save(update_fields=("status",))


def reset_manual_invoice_booking(invoice: ManualInvoice) -> None:
    """Remove only manual booking entries and return the invoice to draft."""
    with db_transaction.atomic():
        locked_invoice = ManualInvoice.objects.select_for_update().get(
            pk=invoice.pk
        )
        ManualInvoiceEntry.objects.filter(manual_invoice=locked_invoice).delete()
        locked_invoice.status = ManualInvoice.Status.DRAFT
        locked_invoice.save(update_fields=("status", "updated_at"))
