import json

from django import template


register = template.Library()


@register.filter
def json_input_value(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"))
