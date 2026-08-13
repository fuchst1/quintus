"""Global, period-independent counts for the bookkeeping sidebar."""

from django.db.models import Q

from .models import BankTransaction, ManualInvoice


def calculate_sidebar_counts() -> dict[str, int]:
    """Return global workflow counts without loading source objects.

    Counts are based on source transactions/invoices, never on their booking
    rows.  This prevents a split booking from inflating a sidebar badge.
    """
    incomplete_ready_bank = Q(
        status__in=(
            BankTransaction.Status.REVIEWED,
            BankTransaction.Status.BOOKED,
        ),
        booking_entries__isnull=True,
    )
    open_bank_count = (
        BankTransaction.objects.filter(
            Q(
                status__in=(
                    BankTransaction.Status.IMPORTED,
                    BankTransaction.Status.MATCHED,
                )
            )
            | incomplete_ready_bank
        )
        .distinct()
        .count()
    )
    open_manual_count = (
        ManualInvoice.objects.filter(
            Q(status=ManualInvoice.Status.DRAFT)
            | Q(
                status=ManualInvoice.Status.READY,
                booking_entries__isnull=True,
            )
        )
        .distinct()
        .count()
    )
    ready_bank_count = BankTransaction.objects.filter(
        status__in=(
            BankTransaction.Status.REVIEWED,
            BankTransaction.Status.BOOKED,
        )
    ).count()
    ready_manual_count = ManualInvoice.objects.filter(
        status=ManualInvoice.Status.READY,
    ).count()
    return {
        "sidebar_open_count": open_bank_count + open_manual_count,
        "sidebar_ready_count": ready_bank_count + ready_manual_count,
    }


def sidebar_context(request) -> dict[str, int]:
    """Expose the global counts once per request for all Bookkeeping views."""
    cached = getattr(request, "_bookkeeping_sidebar_counts", None)
    if cached is None:
        cached = calculate_sidebar_counts()
        request._bookkeeping_sidebar_counts = cached
    return dict(cached)
