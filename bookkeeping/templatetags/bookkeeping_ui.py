"""Template tags for reusable Core Ledger components."""

from django import template

from ..ui_components import resolve_status


register = template.Library()


@register.inclusion_tag("bookkeeping/new_ui/components/_status_badge.html")
def status_badge(family: str, value: object) -> dict[str, object]:
    """Render a centrally mapped, family-aware status badge."""

    status = resolve_status(family, value)
    return {
        "status": status,
        "label": status.label,
        "variant": status.variant,
        "icon": status.icon,
        "known": status.known,
    }
