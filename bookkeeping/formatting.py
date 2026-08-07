from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY_QUANTUM = Decimal("0.01")


def format_austrian_decimal(value):
    """Format a Decimal with Austrian separators and two decimal places."""
    if value in (None, ""):
        return ""
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        decimal_value = decimal_value.quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        sign = "-" if decimal_value < 0 else ""
        grouped = format(abs(decimal_value), ",.2f")
    except (InvalidOperation, TypeError, ValueError):
        return ""
    return f"{sign}{grouped.replace(',', '_').replace('.', ',').replace('_', '.')}"


def format_austrian_money(value, currency):
    formatted_value = format_austrian_decimal(value)
    if not formatted_value:
        return "–"
    return f"{formatted_value} {currency or '–'}"


def normalize_austrian_decimal_input(value):
    """Normalize Austrian or decimal-point input for DecimalField parsing."""
    if not isinstance(value, str):
        return value

    text = value.strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        return text

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            return text.replace(".", "").replace(",", ".")
        return text.replace(",", "")
    if "," in text:
        return text.replace(",", ".")
    return text
