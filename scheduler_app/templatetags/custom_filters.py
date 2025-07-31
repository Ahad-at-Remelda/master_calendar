from django import template

register = template.Library()

@register.filter
def to_int(value, arg):
    return range(value, arg)
