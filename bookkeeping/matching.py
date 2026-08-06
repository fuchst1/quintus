import re
from collections import defaultdict

from django.db import transaction

from .models import BankTransaction, MatchingRule, normalize_iban


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

    with transaction.atomic():
        eligible_transactions = list(
            BankTransaction.objects.filter(
                status__in=(
                    BankTransaction.Status.IMPORTED,
                    BankTransaction.Status.MATCHED,
                )
            )
        )
        for bank_transaction in eligible_transactions:
            if (
                bank_transaction.status == BankTransaction.Status.MATCHED
                or bank_transaction.matched_rule_id
            ):
                bank_transaction.matched_rule = None
                bank_transaction.status = BankTransaction.Status.IMPORTED
                bank_transaction.save(update_fields=("matched_rule", "status"))

            exact_key = (
                normalize_iban(bank_transaction.partner_iban),
                bank_transaction.direction,
                abs(bank_transaction.amount),
            )
            exact_matches = exact_candidates.get(exact_key, [])
            if len(exact_matches) == 1:
                bank_transaction.matched_rule = exact_matches[0]
                bank_transaction.status = BankTransaction.Status.MATCHED
                bank_transaction.save(update_fields=("matched_rule", "status"))
                matched_count += 1
                continue
            if len(exact_matches) > 1:
                ambiguous_count += 1
                continue

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
                bank_transaction.matched_rule = regex_matches[0]
                bank_transaction.status = BankTransaction.Status.MATCHED
                bank_transaction.save(update_fields=("matched_rule", "status"))
                matched_count += 1
            elif len(regex_matches) > 1:
                ambiguous_count += 1
            else:
                unmatched_count += 1

    return matched_count, unmatched_count, ambiguous_count
