from .choices import CATEGORY_CHOICES


def _description_from_choice(label):
    _code, separator, description = label.partition(" – ")
    return description if separator else label


CATEGORY_DESCRIPTIONS = {
    code: _description_from_choice(label)
    for code, label in CATEGORY_CHOICES
}


def category_description(value):
    value = str(value or "")
    return CATEGORY_DESCRIPTIONS.get(value, value)


def category_description_choices():
    return [
        ("", ""),
        *sorted(
            CATEGORY_DESCRIPTIONS.items(),
            key=lambda item: item[1].casefold(),
        ),
    ]
