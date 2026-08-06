import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.db import transaction as db_transaction
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import DeleteView, TemplateView, UpdateView

from .matching import match_imported_transactions
from .forms import MatchingRuleForm
from .models import BankTransaction, MatchingRule


def _display_matching_rule(rule):
    expected_amount = (
        f"{rule.expected_amount:.2f}"
        if rule.expected_amount is not None
        else "–"
    )
    return {
        "id": rule.pk,
        "name": rule.name,
        "direction": rule.get_direction_display(),
        "direction_code": rule.direction,
        "match_type": rule.get_match_type_display(),
        "iban": rule.iban or "–",
        "expected_amount": expected_amount,
        "text_pattern": rule.text_pattern or "–",
        "active": rule.active,
        "status": "Aktiv" if rule.active else "Inaktiv",
    }


def _protected_rule_transactions(rule):
    return BankTransaction.objects.filter(
        matched_rule=rule,
        status__in=(
            BankTransaction.Status.REVIEWED,
            BankTransaction.Status.BOOKED,
        ),
    )


def _reset_matched_rule_transactions(rule):
    return BankTransaction.objects.filter(
        matched_rule=rule,
        status=BankTransaction.Status.MATCHED,
    ).update(
        matched_rule=None,
        status=BankTransaction.Status.IMPORTED,
    )


class BookkeepingOverviewView(TemplateView):
    template_name = "bookkeeping/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        saved_transactions = list(
            BankTransaction.objects.select_related("matched_rule").order_by(
                "-booking_date", "-imported_at"
            )
        )
        context["transactions"] = [
            self._display_saved_transaction(transaction)
            for transaction in saved_transactions
        ]
        context["show_preview"] = bool(saved_transactions)
        context.setdefault("error_message", "")
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "run_matching":
            matched_count, unmatched_count, ambiguous_count = (
                match_imported_transactions()
            )
            messages.success(
                request,
                f"{matched_count} zugeordnet, {unmatched_count} ohne Treffer, "
                f"{ambiguous_count} mehrdeutig.",
            )
            return redirect("bookkeeping_overview")

        uploaded_file = request.FILES.get("json_file")
        if uploaded_file is None:
            return self.render_to_response(
                self.get_context_data(error_message="Bitte eine JSON-Datei auswählen.")
            )

        try:
            payload = json.load(uploaded_file)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            return self.render_to_response(
                self.get_context_data(error_message="Die Datei ist kein gültiges JSON.")
            )

        if not isinstance(payload, list):
            return self.render_to_response(
                self.get_context_data(
                    error_message="Die JSON-Wurzel muss ein Array sein."
                )
            )

        try:
            import_payloads = [self._build_import_payload(item) for item in payload]
        except ValueError as exc:
            return self.render_to_response(
                self.get_context_data(error_message=str(exc))
            )

        imported_count, existing_count = self._persist_transactions(import_payloads)
        matched_count, unmatched_count, ambiguous_count = (
            match_imported_transactions()
        )
        messages.success(
            request,
            f"{imported_count} Transaktionen importiert, "
            f"{existing_count} bereits vorhanden.",
        )
        messages.info(
            request,
            f"{matched_count} zugeordnet, {unmatched_count} ohne Treffer, "
            f"{ambiguous_count} mehrdeutig.",
        )
        return redirect("bookkeeping_overview")

    @classmethod
    def _build_import_payload(cls, transaction):
        if not isinstance(transaction, dict):
            raise ValueError("Eine Transaktion ist ungültig.")

        booking_date = cls._parse_booking_date(transaction.get("booking"))
        if booking_date is None:
            raise ValueError("Eine Transaktion enthält kein gültiges Buchungsdatum.")

        amount = transaction.get("amount")
        if not isinstance(amount, dict):
            raise ValueError("Eine Transaktion enthält keinen gültigen Betrag.")
        converted_amount, direction = cls._parse_amount(amount)

        partner_account = transaction.get("partnerAccount")
        if not isinstance(partner_account, dict):
            partner_account = {}

        currency = cls._text_or_empty(amount.get("currency")) or "EUR"
        if len(currency) > 3:
            raise ValueError("Eine Transaktion enthält eine ungültige Währung.")

        reference = cls._text_or_empty(transaction.get("reference"))
        purpose = reference or cls._text_or_empty(transaction.get("receiverReference"))

        return {
            "source_hash": cls._source_hash(transaction),
            "booking_date": booking_date,
            "partner_name": cls._text_or_empty(transaction.get("partnerName")),
            "partner_iban": cls._text_or_empty(partner_account.get("iban")),
            "amount": converted_amount,
            "currency": currency,
            "purpose": purpose,
            "direction": direction,
            "source": BankTransaction.Source.BANK_IMPORT,
            "status": BankTransaction.Status.IMPORTED,
        }

    @classmethod
    def _persist_transactions(cls, import_payloads):
        imported_count = 0
        existing_count = 0
        source_hashes = [payload["source_hash"] for payload in import_payloads]

        with db_transaction.atomic():
            existing_hashes = set(
                BankTransaction.objects.filter(source_hash__in=source_hashes).values_list(
                    "source_hash", flat=True
                )
            )
            for payload in import_payloads:
                source_hash = payload["source_hash"]
                if source_hash in existing_hashes:
                    existing_count += 1
                    continue
                BankTransaction.objects.create(**payload)
                existing_hashes.add(source_hash)
                imported_count += 1

        return imported_count, existing_count

    @staticmethod
    def _source_hash(transaction):
        serialized = json.dumps(
            transaction,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _parse_booking_date(cls, value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        text = cls._text_or_empty(value)
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(text[:10])
            except ValueError:
                return None

    @classmethod
    def _parse_amount(cls, amount):
        value = amount.get("value")
        if value is None:
            raise ValueError("Eine Transaktion enthält keinen gültigen Betrag.")
        try:
            precision = int(amount.get("precision") or 0)
            if precision < 0:
                raise ValueError
            converted = Decimal(str(value)) / (Decimal("10") ** precision)
            converted = converted.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            raise ValueError("Eine Transaktion enthält keinen gültigen Betrag.") from None

        if converted > 0:
            return converted, BankTransaction.Direction.INCOMING
        if converted < 0:
            return converted, BankTransaction.Direction.OUTGOING
        raise ValueError("Eine Transaktion enthält keinen gültigen Betrag.")

    @classmethod
    def _display_saved_transaction(cls, transaction):
        direction_labels = {
            BankTransaction.Direction.INCOMING: "Eingang",
            BankTransaction.Direction.OUTGOING: "Ausgang",
        }
        direction = direction_labels.get(transaction.direction, "–")
        direction_code = transaction.direction if direction != "–" else ""
        return {
            "booking_date": transaction.booking_date.strftime("%d.%m.%Y"),
            "name": cls._text_or_dash(transaction.partner_name),
            "iban": cls._text_or_dash(transaction.partner_iban),
            "amount": cls._format_saved_amount(transaction.amount, transaction.currency),
            "direction_code": direction_code,
            "direction": direction,
            "purpose": cls._text_or_dash(transaction.purpose),
            "status": transaction.get_status_display(),
            "matched_rule": (
                transaction.matched_rule.name
                if transaction.matched_rule_id
                else "–"
            ),
        }

    @classmethod
    def _format_saved_amount(cls, amount, currency):
        try:
            formatted = Decimal(str(amount)).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        except (InvalidOperation, TypeError, ValueError):
            return "–"
        return f"{formatted:.2f} {cls._text_or_dash(currency)}"

    @staticmethod
    def _text_or_empty(value):
        text = str(value).strip() if value is not None else ""
        return text

    @classmethod
    def _text_or_dash(cls, value):
        return cls._text_or_empty(value) or "–"


class MatchingRuleListView(TemplateView):
    template_name = "bookkeeping/matching_rules.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["matching_rules"] = [
            _display_matching_rule(rule)
            for rule in MatchingRule.objects.order_by("-created_at")
        ]
        context.setdefault("matching_rule_form", MatchingRuleForm())
        return context

    def post(self, request, *args, **kwargs):
        matching_rule_form = MatchingRuleForm(request.POST)
        if matching_rule_form.is_valid():
            matching_rule_form.save()
            messages.success(request, "Matching-Regel angelegt.")
            return redirect("matching_rule_list")
        return self.render_to_response(
            self.get_context_data(
                matching_rule_form=matching_rule_form,
                matching_rule_error="Bitte prüfen Sie die Angaben zur Matching-Regel.",
            )
        )


class MatchingRuleEditView(UpdateView):
    model = MatchingRule
    form_class = MatchingRuleForm
    template_name = "bookkeeping/matching_rule_edit.html"
    success_url = reverse_lazy("matching_rule_list")

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if _protected_rule_transactions(self.object).exists():
            messages.error(
                request,
                "Diese Matching-Regel kann nicht bearbeitet werden, "
                "weil sie geprüften oder gebuchten Transaktionen zugeordnet ist.",
            )
            return redirect("matching_rule_list")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        with db_transaction.atomic():
            response = super().form_valid(form)
            _reset_matched_rule_transactions(self.object)
        messages.success(self.request, "Matching-Regel gespeichert.")
        return response


class MatchingRuleDeleteView(DeleteView):
    model = MatchingRule
    template_name = "bookkeeping/matching_rule_delete.html"
    success_url = reverse_lazy("matching_rule_list")

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if _protected_rule_transactions(self.object).exists():
            messages.error(
                request,
                "Diese Matching-Regel kann nicht gelöscht werden, "
                "weil sie geprüften oder gebuchten Transaktionen zugeordnet ist.",
            )
            return redirect("matching_rule_list")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        rule_name = self.object.name
        with db_transaction.atomic():
            _reset_matched_rule_transactions(self.object)
            response = super().form_valid(form)
        messages.success(self.request, f'Matching-Regel „{rule_name}“ gelöscht.')
        return response
