# scheduler_app/templatetags/calendar_extras.py

from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Custom template filter to allow accessing a dictionary item with a variable key.
    Usage: {{ my_dictionary|get_item:my_variable_key }}
    """
    return dictionary.get(key)