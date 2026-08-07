import re
from collections import defaultdict
from decimal import Decimal

from django.db import transaction

from .choices import RECEIPT_GROUP_BANK
from .models import BookingEntry, BankTransaction, MatchingRule, normalize_iban


SNAPSHOT_ERROR = (
    "Die Excel-Ergebniszeilen sind für eine automatische Buchung "
    "unvollständig oder nicht verwendbar. Bitte erfassen Sie die "
    "Buchungsdaten manuell."
)


class MatchingResult(tuple):
    """Legacy-compatible three-value result with detailed match counters."""

    def __new__(
        cls,
        matched_count,
        unmatched_count,
        ambiguous_count,
        auto_ready_count=0,
        incomplete_count=0,
    ):
        result = super().__new__(
            cls,
            (matched_count, unmatched_count, ambiguous_count),
        )
        result.auto_ready_count = auto_ready_count
        result.incomplete_count = incomplete_count
        return result

    @property
    def matched_count(self):
        return self[0]

    @property
    def unmatched_count(self):
        return self[1]

    @property
    def ambiguous_count(self):
        return self[2]


def build_booking_entry_snapshot(bank_transaction):
    """Build independent BookingEntry values without writing any rows."""
    if not bank_transaction.matched_rule_id:
        return None, None
    templates = list(
        bank_transaction.matched_rule.booking_templates.order_by("position", "id")
    )
    if not templates:
        return None, None

    transaction_amount = abs(bank_transaction.amount).quantize(Decimal("0.01"))
    fixed_amounts = [
        template.gross_amount
        for template in templates
        if template.gross_amount is not None
    ]
    if any(amount <= 0 for amount in fixed_amounts):
        return None, SNAPSHOT_ERROR

    fixed_total = sum(fixed_amounts, Decimal("0")).quantize(Decimal("0.01"))
    rest_templates = [
        template for template in templates if template.gross_amount is None
    ]
    if fixed_total > transaction_amount or len(rest_templates) > 1:
        return None, SNAPSHOT_ERROR
    if not rest_templates and fixed_total != transaction_amount:
        return None, SNAPSHOT_ERROR

    remaining_amount = (transaction_amount - fixed_total).quantize(Decimal("0.01"))
    sign = Decimal("-1") if bank_transaction.amount < 0 else Decimal("1")
    payment_date = bank_transaction.value_date or bank_transaction.booking_date
    initials = []
    for template in templates:
        amount = template.gross_amount
        if amount is None:
            amount = remaining_amount
        amount = (amount * sign).quantize(Decimal("0.01"))
        initial = {
            "receipt_group": RECEIPT_GROUP_BANK,
            "receipt_number": str(payment_date.month),
            "payment_date": payment_date,
            "booking_text": template.booking_text or bank_transaction.purpose,
            "invoice_number": template.invoice_number or "",
            "partner_name": template.partner_name or bank_transaction.partner_name,
            "gross_amount": amount,
            "vat_symbol": template.vat_symbol,
            "category": template.category,
        }
        if not all(
            initial[field_name]
            for field_name in (
                "booking_text",
                "partner_name",
                "vat_symbol",
                "category",
            )
        ):
            return None, SNAPSHOT_ERROR
        initials.append(initial)

    if sum(
        (initial["gross_amount"] for initial in initials),
        Decimal("0"),
    ) != bank_transaction.amount:
        return None, SNAPSHOT_ERROR
    return initials, None


def _save_automatic_booking_snapshot(bank_transaction, initials):
    BookingEntry.objects.bulk_create(
        [
            BookingEntry(bank_transaction=bank_transaction, **initial)
            for initial in initials
        ]
    )
    bank_transaction.status = BankTransaction.Status.REVIEWED
    bank_transaction.save(update_fields=("status",))


def _normalized_transaction_text(bank_transaction):
    return " ".join(
        f"{bank_transaction.partner_name} {bank_transaction.purpose}".split()
    )


def match_imported_transactions():
    """Match each eligible transaction against exact rules before regex rules."""
    exact_candidates = defaultdict(list)
    regex_rules = []
    active_rules = MatchingRule.objects.filter(active=True)
    for rule in active_rules:
        if rule.match_type == MatchingRule.MatchType.EXACT:
            if (
                not rule.iban
                or rule.expected_amount is None
                or rule.expected_amount <= 0
                or rule.text_pattern.strip()
            ):
                continue
            key = (normalize_iban(rule.iban), rule.direction, rule.expected_amount)
            exact_candidates[key].append(rule)
        elif rule.match_type == MatchingRule.MatchType.REGEX:
            if rule.expected_amount is not None or not rule.text_pattern.strip():
                continue
            try:
                pattern = re.compile(rule.text_pattern, re.IGNORECASE)
            except re.error:
                continue
            regex_rules.append((rule, pattern))

    matched_count = 0
    unmatched_count = 0
    ambiguous_count = 0
    auto_ready_count = 0
    incomplete_count = 0

    eligible_transactions = list(
        BankTransaction.objects.filter(
            status=BankTransaction.Status.IMPORTED,
        )
    )
    for bank_transaction in eligible_transactions:
        with transaction.atomic():
            if bank_transaction.matched_rule_id:
                bank_transaction.matched_rule = None
                bank_transaction.save(update_fields=("matched_rule",))

            exact_key = (
                normalize_iban(bank_transaction.partner_iban),
                bank_transaction.direction,
                abs(bank_transaction.amount),
            )
            exact_matches = exact_candidates.get(exact_key, [])
            matched_rule = None
            if len(exact_matches) == 1:
                matched_rule = exact_matches[0]
            elif len(exact_matches) > 1:
                ambiguous_count += 1
                continue
            else:
                transaction_text = _normalized_transaction_text(bank_transaction)
                regex_matches = []
                for rule, pattern in regex_rules:
                    if rule.direction != bank_transaction.direction:
                        continue
                    if rule.iban and normalize_iban(rule.iban) != normalize_iban(
                        bank_transaction.partner_iban
                    ):
                        continue
                    if pattern.search(transaction_text):
                        regex_matches.append(rule)

                if len(regex_matches) == 1:
                    matched_rule = regex_matches[0]
                elif len(regex_matches) > 1:
                    ambiguous_count += 1
                    continue
                else:
                    unmatched_count += 1
                    continue

            bank_transaction.matched_rule = matched_rule
            bank_transaction.status = BankTransaction.Status.MATCHED
            bank_transaction.save(update_fields=("matched_rule", "status"))
            matched_count += 1

            if bank_transaction.booking_entries.exists():
                incomplete_count += 1
                continue

            initials, snapshot_error = build_booking_entry_snapshot(
                bank_transaction
            )
            if snapshot_error or not initials:
                incomplete_count += 1
                continue

            _save_automatic_booking_snapshot(bank_transaction, initials)
            auto_ready_count += 1

    return MatchingResult(
        matched_count,
        unmatched_count,
        ambiguous_count,
        auto_ready_count,
        incomplete_count,
    )
