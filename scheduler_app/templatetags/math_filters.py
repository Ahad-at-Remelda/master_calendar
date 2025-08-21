# scheduler_app/templatetags/math_filters.py

from django import template

register = template.Library()

@register.filter
def multiply(value, arg):
    """Multiplies the value by the arg."""
    try:
        # Ensure values are numeric before multiplying
        return float(value) * float(arg)
    except (ValueError, TypeError):
        # Return an empty string or 0 if values are not numbers
        return ''

@register.filter
def sub(value, arg):
    """Subtracts the arg from the value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return ''

@register.filter
def div(value, arg):
    """Divides the value by the arg."""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return ''