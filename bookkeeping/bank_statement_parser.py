from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from .formatting import format_austrian_decimal

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - dependency is installed in deployment
    PdfReader = None


class BankStatementParseError(ValueError):
    """A German, user-facing error while reading a bank statement PDF."""


@dataclass(frozen=True)
class ParsedBankStatement:
    iban: str
    statement_number: int
    statement_year: int
    statement_date: date
    opening_balance: Decimal
    total_credits: Decimal
    total_debits: Decimal
    closing_balance: Decimal

    @property
    def booking_month(self) -> str:
        return self.statement_date.strftime("%Y-%m")

    @property
    def booking_quarter(self) -> str:
        quarter = ((self.statement_date.month - 1) // 3) + 1
        return f"{self.statement_date.year}-Q{quarter}"


MONEY_PATTERN = re.compile(
    r"(?<!\d)(?:-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}-?)(?!\d)"
)
TRANSACTION_DATE_PATTERN = re.compile(
    r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b"
)
FOOTER_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?P<iban>AT\d{18})[ \t]+"
    r"(?P<date>\d{2}\.\d{2}\.\d{4})[ \t]+\d{2}:\d{2}"
    r"(?:[ \t]+\d+[ \t]+(?P<statement_number>\d+)[ \t]+\d+)?"
    r"(?=[ \t]|$)",
    re.IGNORECASE | re.MULTILINE,
)


def _normalize_text(value: str) -> str:
    return "\n".join(
        " ".join(line.replace("\xa0", " ").split())
        for line in value.splitlines()
        if line.strip()
    )


def _parse_austrian_amount(raw_value: str) -> Decimal:
    normalized = str(raw_value or "").strip().replace(" ", "")
    trailing_minus = normalized.endswith("-")
    leading_minus = normalized.startswith("-")
    normalized = normalized.rstrip("-").lstrip("-")
    normalized = normalized.replace(".", "").replace(",", ".")
    try:
        value = Decimal(normalized).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise BankStatementParseError(
            f"Der Betrag '{raw_value}' konnte nicht gelesen werden."
        ) from None
    if trailing_minus or leading_minus:
        return -value
    return value


def _is_transaction_like_line(line: str) -> bool:
    normalized = line.casefold()
    return bool(
        TRANSACTION_DATE_PATTERN.search(line)
        or any(
            marker in normalized
            for marker in (
                "buchungstext",
                "booking text",
                "valuta",
                "value",
                "beträge",
                "amounts",
            )
        )
    )


def _extract_labeled_amounts(
    lines: list[str],
    labels: tuple[str, ...],
) -> list[Decimal]:
    values = []
    for line_index, line in enumerate(lines):
        for label in labels:
            match = re.search(re.escape(label), line, re.IGNORECASE)
            if match is None:
                continue

            candidate_lines = [line[match.end() :]]
            following_lines = 0
            for following_line in lines[line_index + 1 :]:
                if not following_line.strip():
                    continue
                candidate_lines.append(following_line)
                following_lines += 1
                if following_lines == 2:
                    break

            amount = None
            for candidate_line in candidate_lines:
                if _is_transaction_like_line(candidate_line):
                    continue
                amount_match = MONEY_PATTERN.search(candidate_line)
                if amount_match is not None:
                    amount = _parse_austrian_amount(amount_match.group(0))
                    break
            if amount is not None:
                values.append(amount)
            break
    return values


def _extract_labeled_amount(
    lines: list[str],
    labels: tuple[str, ...],
    field_label: str,
    multiple_value_label: str,
) -> Decimal:
    values = _extract_labeled_amounts(lines, labels)
    if not values:
        raise BankStatementParseError(f"{field_label} konnte im PDF nicht gefunden werden.")
    if len(set(values)) > 1:
        raise BankStatementParseError(
            f"Im PDF wurden unterschiedliche Werte für {multiple_value_label} gefunden."
        )
    return values[0]


def _extract_footer_data(text: str) -> tuple[str, date, tuple[int, ...]]:
    matches = list(FOOTER_PATTERN.finditer(text))
    if not matches:
        raise BankStatementParseError(
            "Das Auszugsdatum konnte im PDF nicht gefunden werden."
        )

    footer_dates = []
    footer_ibans = []
    footer_statement_numbers = []
    for match in matches:
        raw_date = match.group("date")
        try:
            parsed_date = datetime.strptime(raw_date, "%d.%m.%Y").date()
        except ValueError:
            raise BankStatementParseError(
                f"Das Auszugsdatum in der PDF-Fußzeile ist ungültig: {raw_date}."
            ) from None
        footer_dates.append(parsed_date)
        footer_ibans.append(match.group("iban").upper())
        raw_statement_number = match.group("statement_number")
        if raw_statement_number is not None:
            footer_statement_numbers.append(int(raw_statement_number))

    distinct_dates = sorted(set(footer_dates))
    if len(distinct_dates) > 1:
        displayed_dates = ", ".join(
            item.strftime("%d.%m.%Y") for item in distinct_dates
        )
        raise BankStatementParseError(
            "Widersprüchliche Auszugsdaten in den PDF-Fußzeilen gefunden: "
            f"{displayed_dates}."
        )

    if len(set(footer_ibans)) > 1:
        raise BankStatementParseError(
            "Widersprüchliche IBANs in den PDF-Fußzeilen gefunden."
        )

    distinct_statement_numbers = tuple(sorted(set(footer_statement_numbers)))
    if len(distinct_statement_numbers) > 1:
        displayed_numbers = ", ".join(
            f"{item:03d}" for item in distinct_statement_numbers
        )
        raise BankStatementParseError(
            "Widersprüchliche Auszugsnummern in den PDF-Fußzeilen gefunden: "
            f"{displayed_numbers}."
        )

    return footer_ibans[0], distinct_dates[0], distinct_statement_numbers


def _extract_text(pdf_file) -> str:
    if PdfReader is None:
        raise BankStatementParseError(
            "PDF-Auslesung ist nicht verfügbar. Bitte pypdf installieren."
        )
    try:
        if hasattr(pdf_file, "seek"):
            pdf_file.seek(0)
        reader = PdfReader(pdf_file)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise BankStatementParseError(
            "Das PDF konnte nicht gelesen werden. Bitte einen lesbaren Kontoauszug hochladen."
        ) from exc
    finally:
        if hasattr(pdf_file, "seek"):
            pdf_file.seek(0)
    if not text.strip():
        raise BankStatementParseError("Im PDF wurde kein lesbarer Text gefunden.")
    return _normalize_text(text)


def parse_bank_statement(pdf_file) -> ParsedBankStatement:
    text = _extract_text(pdf_file)
    lines = text.splitlines()

    iban, statement_date, footer_statement_numbers = _extract_footer_data(text)

    statement_match = re.search(
        r"(?:kontoauszug|auszug|auszugsnummer)\s*(?:nr\.?|nummer)?\s*[:#]?\s*"
        r"(\d{1,})\s*/\s*(\d{4})",
        text,
        re.IGNORECASE,
    )
    statement_number = None
    statement_year = None
    if statement_match is not None:
        statement_number = int(statement_match.group(1))
        statement_year = int(statement_match.group(2))
    else:
        number_match = re.search(
            r"(?:auszugsnummer|kontoauszugsnummer)\s*(?:nr\.?|nummer)?\s*[:#]?\s*(\d{1,})",
            text,
            re.IGNORECASE,
        )
        if number_match is not None:
            statement_number = int(number_match.group(1))
        year_match = re.search(
            r"(?:auszugsjahr|kontoauszugsjahr)\s*[:#]?\s*(\d{4})",
            text,
            re.IGNORECASE,
        )
        if year_match is not None:
            statement_year = int(year_match.group(1))

    if statement_number is None:
        if footer_statement_numbers:
            statement_number = footer_statement_numbers[0]
        else:
            raise BankStatementParseError(
                "Die Auszugsnummer konnte im PDF nicht gefunden werden."
            )
    if statement_year is None:
        statement_year = statement_date.year

    opening_balance = _extract_labeled_amount(
        lines,
        ("Alter Kontostand", "Anfangssaldo", "Saldo alt"),
        "Der alte Kontostand",
        "den alten Kontostand",
    )
    total_credits = abs(
        _extract_labeled_amount(
            lines,
            ("Gutschriften", "Summe Gutschriften"),
            "Die Gutschriften",
            "die Gutschriften",
        )
    )
    total_debits = abs(
        _extract_labeled_amount(
            lines,
            ("Belastungen", "Summe Belastungen"),
            "Die Belastungen",
            "die Belastungen",
        )
    )
    closing_balance = _extract_labeled_amount(
        lines,
        ("Neuer Kontostand", "Endsaldo", "Saldo neu"),
        "Der neue Kontostand",
        "den neuen Kontostand",
    )
    calculated_closing = opening_balance + total_credits - total_debits
    if calculated_closing != closing_balance:
        raise BankStatementParseError(
            "Die Kontostandsrechnung stimmt nicht: "
            f"{format_austrian_decimal(opening_balance)} + "
            f"{format_austrian_decimal(total_credits)} - "
            f"{format_austrian_decimal(total_debits)} = "
            f"{format_austrian_decimal(calculated_closing)}, erwartet wären "
            f"{format_austrian_decimal(closing_balance)} EUR."
        )

    return ParsedBankStatement(
        iban=iban,
        statement_number=statement_number,
        statement_year=statement_year,
        statement_date=statement_date,
        opening_balance=opening_balance,
        total_credits=total_credits,
        total_debits=total_debits,
        closing_balance=closing_balance,
    )


def pdf_bytes(pdf_file) -> bytes:
    if hasattr(pdf_file, "seek"):
        pdf_file.seek(0)
    content = pdf_file.read()
    if hasattr(pdf_file, "seek"):
        pdf_file.seek(0)
    return content if isinstance(content, bytes) else bytes(content)


def pdf_stream(pdf_file) -> BytesIO:
    return BytesIO(pdf_bytes(pdf_file))
