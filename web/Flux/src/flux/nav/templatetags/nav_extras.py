from django import template


register = template.Library()


@register.filter
def get_item(value, key):
    if value is None:
        return None
    return value.get(key)


@register.filter
def option_label(options, value):
    if value in (None, ""):
        return ""
    for option in options or []:
        if option.value == str(value):
            return option.label
    return value
