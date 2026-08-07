from django import template

from ..formatting import format_austrian_decimal, format_austrian_money


register = template.Library()


@register.filter
def austrian_decimal(value):
    return format_austrian_decimal(value)


@register.filter
def austrian_money(value, currency):
    return format_austrian_money(value, currency)
