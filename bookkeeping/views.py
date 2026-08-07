import hashlib
import json
import re
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import DeleteView, TemplateView, UpdateView

from .matching import match_imported_transactions
from .forms import BankTransactionNoteForm, MatchingRuleForm
from .models import BankTransaction, MatchingRule


STATUS_NAVIGATION = (
    {
        "value": BankTransaction.Status.IMPORTED,
        "label": "Offen",
        "heading": "Offene Transaktionen",
        "empty_label": "offenen",
        "icon": "bi-inbox",
    },
    {
        "value": BankTransaction.Status.MATCHED,
        "label": "Zugeordnet",
        "heading": "Zugeordnete Transaktionen",
        "empty_label": "zugeordneten",
        "icon": "bi-check2-square",
    },
    {
        "value": BankTransaction.Status.REVIEWED,
        "label": "Geprüft",
        "heading": "Geprüfte Transaktionen",
        "empty_label": "geprüften",
        "icon": "bi-search",
    },
    {
        "value": BankTransaction.Status.BOOKED,
        "label": "Exportiert",
        "heading": "Exportierte Transaktionen",
        "empty_label": "exportierten",
        "icon": "bi-box-arrow-up-right",
    },
)
STATUS_VALUES = {item["value"] for item in STATUS_NAVIGATION}
STATUS_DETAILS = {item["value"]: item for item in STATUS_NAVIGATION}
GERMAN_MONTH_NAMES = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)
MONTH_PATTERN = re.compile(r"^(?P<year>[0-9]{4})-(?P<month>0[1-9]|1[0-2])$")


def _parse_month(value):
    if not isinstance(value, str):
        return None
    match = MONTH_PATTERN.fullmatch(value)
    if match is None:
        return None
    try:
        return date(int(match.group("year")), int(match.group("month")), 1)
    except ValueError:
        return None


def _month_label(month_key):
    month = _parse_month(month_key)
    if month is None:
        return ""
    return f"{GERMAN_MONTH_NAMES[month.month - 1]} {month.year}"


def _month_bounds(month_key):
    month = _parse_month(month_key)
    if month is None:
        return None
    return month, date(month.year, month.month, monthrange(month.year, month.month)[1])


def _month_filter(month_key):
    bounds = _month_bounds(month_key)
    if bounds is None:
        return {}
    start, end = bounds
    return {"booking_date__gte": start, "booking_date__lte": end}


def _overview_url(status, month=None):
    query = {"status": status}
    if month is not None:
        query["month"] = month
    return f"{reverse('bookkeeping_overview')}?{urlencode(query)}"


def _note_preview(note, max_length=90):
    normalized_note = " ".join(str(note or "").split())
    if len(normalized_note) <= max_length:
        return normalized_note, False
    return f"{normalized_note[: max_length - 1]}…", True


def _bookkeeping_navigation_context(request, filter_params=None):
    params = filter_params if filter_params is not None else request.GET
    requested_status = params.get("status")
    selected_status = (
        requested_status if requested_status in STATUS_VALUES else BankTransaction.Status.IMPORTED
    )

    available_month_keys = sorted(
        {
            booking_date.strftime("%Y-%m")
            for booking_date in BankTransaction.objects.values_list(
                "booking_date", flat=True
            )
        },
        reverse=True,
    )
    if "month" in params and params.get("month") == "":
        selected_month = ""
    else:
        requested_month = params.get("month")
        selected_month = (
            requested_month
            if requested_month in available_month_keys and _parse_month(requested_month)
            else (available_month_keys[0] if available_month_keys else "")
        )

    count_query = BankTransaction.objects
    if selected_month:
        count_query = count_query.filter(**_month_filter(selected_month))
    counts_by_status = {
        row["status"]: row["count"]
        for row in count_query.values("status").annotate(count=Count("id"))
    }
    status_navigation = [
        {
            **item,
            "count": counts_by_status.get(item["value"], 0),
            "url": _overview_url(
                item["value"],
                selected_month if selected_month or available_month_keys else None,
            ),
            "active": (
                request.resolver_match.url_name
                in {"bookkeeping_overview", "bank_transaction_note"}
                and selected_status == item["value"]
            ),
        }
        for item in STATUS_NAVIGATION
    ]
    selected_status_details = STATUS_DETAILS[selected_status]
    month_suffix = f" für {_month_label(selected_month)}" if selected_month else ""
    return {
        "selected_status": selected_status,
        "selected_status_label": selected_status_details["label"],
        "page_heading": selected_status_details["heading"],
        "selected_month": selected_month,
        "selected_month_label": _month_label(selected_month),
        "available_months": [
            {"value": month_key, "label": _month_label(month_key)}
            for month_key in available_month_keys
        ],
        "status_counts": {
            item["value"]: counts_by_status.get(item["value"], 0)
            for item in STATUS_NAVIGATION
        },
        "status_navigation": status_navigation,
        "empty_state_message": (
            f"Keine {selected_status_details['empty_label']} Transaktionen"
            f"{month_suffix} vorhanden."
        ),
    }


def _display_matching_rule(rule):
    expected_amount = (
        f"{rule.expected_amount:.2f}"
        if rule.expected_amount is not None
        else "–"
    )
    notes_preview, notes_truncated = _note_preview(rule.notes)
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
        "notes": rule.notes,
        "notes_preview": notes_preview,
        "notes_truncated": notes_truncated,
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
        filter_params = kwargs.pop("filter_params", None)
        context = super().get_context_data(**kwargs)
        navigation_context = _bookkeeping_navigation_context(
            self.request,
            filter_params=filter_params,
        )
        selected_transactions = BankTransaction.objects.select_related(
            "matched_rule"
        ).filter(status=navigation_context["selected_status"])
        if navigation_context["selected_month"]:
            selected_transactions = selected_transactions.filter(
                **_month_filter(navigation_context["selected_month"])
            )
        saved_transactions = list(
            selected_transactions.order_by("-booking_date", "-imported_at")
        )
        context["transactions"] = [
            self._display_saved_transaction(transaction)
            for transaction in saved_transactions
        ]
        context["show_preview"] = bool(saved_transactions)
        context.update(navigation_context)
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
            navigation_context = _bookkeeping_navigation_context(
                request,
                filter_params=request.POST,
            )
            return redirect(
                _overview_url(
                    navigation_context["selected_status"],
                    navigation_context["selected_month"],
                )
            )

        uploaded_file = request.FILES.get("json_file")
        if uploaded_file is None:
            return self.render_to_response(
                self.get_context_data(
                    error_message="Bitte eine JSON-Datei auswählen.",
                    filter_params=request.POST,
                )
            )

        try:
            payload = json.load(uploaded_file)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            return self.render_to_response(
                self.get_context_data(
                    error_message="Die Datei ist kein gültiges JSON.",
                    filter_params=request.POST,
                )
            )

        if not isinstance(payload, list):
            return self.render_to_response(
                self.get_context_data(
                    error_message="Die JSON-Wurzel muss ein Array sein.",
                    filter_params=request.POST,
                )
            )

        try:
            import_payloads = [self._build_import_payload(item) for item in payload]
        except ValueError as exc:
            return self.render_to_response(
                self.get_context_data(
                    error_message=str(exc),
                    filter_params=request.POST,
                )
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
        newest_imported_month = max(
            (payload["booking_date"] for payload in import_payloads),
            default=None,
        )
        newest_imported_month_key = (
            newest_imported_month.strftime("%Y-%m")
            if newest_imported_month is not None
            else None
        )
        return redirect(
            _overview_url(
                BankTransaction.Status.IMPORTED,
                newest_imported_month_key,
            )
        )

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
        transaction_notes_preview, transaction_notes_truncated = _note_preview(
            transaction.notes
        )
        matching_rule_notes = (
            transaction.matched_rule.notes
            if transaction.matched_rule_id
            else ""
        )
        matching_rule_notes_preview, matching_rule_notes_truncated = _note_preview(
            matching_rule_notes
        )
        return {
            "id": transaction.pk,
            "booking_date": transaction.booking_date.strftime("%d.%m.%Y"),
            "name": cls._text_or_dash(transaction.partner_name),
            "iban": cls._text_or_dash(transaction.partner_iban),
            "amount": cls._format_saved_amount(transaction.amount, transaction.currency),
            "direction_code": direction_code,
            "direction": direction,
            "purpose": cls._text_or_dash(transaction.purpose),
            "status": (
                "Exportiert"
                if transaction.status == BankTransaction.Status.BOOKED
                else transaction.get_status_display()
            ),
            "matched_rule": (
                transaction.matched_rule.name
                if transaction.matched_rule_id
                else "–"
            ),
            "matching_rule_notes": matching_rule_notes,
            "matching_rule_notes_preview": matching_rule_notes_preview,
            "matching_rule_notes_truncated": matching_rule_notes_truncated,
            "notes": transaction.notes,
            "notes_preview": transaction_notes_preview,
            "notes_truncated": transaction_notes_truncated,
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


class BankTransactionNoteView(TemplateView):
    template_name = "bookkeeping/transaction_note.html"

    def _navigation_context(self):
        return _bookkeeping_navigation_context(self.request)

    def _context_for_transaction(self, bank_transaction, form, navigation_context):
        return {
            **navigation_context,
            "bank_transaction": bank_transaction,
            "form": form,
            "return_url": _overview_url(
                navigation_context["selected_status"],
                navigation_context["selected_month"],
            ),
        }

    def get(self, request, *args, **kwargs):
        bank_transaction = get_object_or_404(
            BankTransaction,
            pk=kwargs["pk"],
        )
        navigation_context = self._navigation_context()
        form = BankTransactionNoteForm(instance=bank_transaction)
        return self.render_to_response(
            self._context_for_transaction(
                bank_transaction,
                form,
                navigation_context,
            )
        )

    def post(self, request, *args, **kwargs):
        bank_transaction = get_object_or_404(
            BankTransaction,
            pk=kwargs["pk"],
        )
        navigation_context = self._navigation_context()
        form = BankTransactionNoteForm(
            request.POST,
            instance=bank_transaction,
        )
        if form.is_valid():
            bank_transaction.notes = form.cleaned_data["notes"]
            bank_transaction.save(update_fields=("notes",))
            messages.success(request, "Anmerkung gespeichert.")
            return redirect(
                _overview_url(
                    navigation_context["selected_status"],
                    navigation_context["selected_month"],
                )
            )
        return self.render_to_response(
            self._context_for_transaction(
                bank_transaction,
                form,
                navigation_context,
            )
        )


class MatchingRuleListView(TemplateView):
    template_name = "bookkeeping/matching_rules.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_bookkeeping_navigation_context(self.request))
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_bookkeeping_navigation_context(self.request))
        return context

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
        notes_only_change = set(form.changed_data) == {"notes"}
        with db_transaction.atomic():
            response = super().form_valid(form)
            if not notes_only_change:
                _reset_matched_rule_transactions(self.object)
        messages.success(self.request, "Matching-Regel gespeichert.")
        return response


class MatchingRuleDeleteView(DeleteView):
    model = MatchingRule
    template_name = "bookkeeping/matching_rule_delete.html"
    success_url = reverse_lazy("matching_rule_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_bookkeeping_navigation_context(self.request))
        return context

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
