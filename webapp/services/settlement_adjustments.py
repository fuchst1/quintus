from __future__ import annotations

SETTLEMENT_ADJUSTMENT_KEYWORDS: tuple[str, ...] = (
    "nachzahl",
    "nachzahlung",
    "nachverrechnung",
    "gutschrift",
    "rueckzahlung",
    "heizkostenabrechnung",
    "betriebskostenabrechnung",
    "abrechnung",
    "ausgleich",
)


def _normalize_text(raw: str) -> str:
    text = (raw or "").casefold()
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def match_settlement_adjustment_text(*parts: str | None) -> tuple[bool, str]:
    normalized_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        normalized = _normalize_text(part.strip())
        if normalized:
            normalized_parts.append(normalized)

    haystack = " ".join(normalized_parts)
    if not haystack:
        return False, ""

    for keyword in SETTLEMENT_ADJUSTMENT_KEYWORDS:
        if keyword in haystack:
            return True, f'Textmuster "{keyword}" erkannt'
    return False, ""


def is_settlement_adjustment_text(partner_name: str | None, purpose_or_text: str | None) -> bool:
    matched, _ = match_settlement_adjustment_text(partner_name, purpose_or_text)
    return matched
