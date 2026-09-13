"""
Dùng trong template:
  {% load properties_tags %}
  <button>{% label "common.button.save" %}</button>
  <p>{% message "contribution.approve.success" points=10 %}</p>
"""
from django import template

from apps.core.properties import label as _label
from apps.core.properties import message as _message

register = template.Library()


@register.simple_tag(name="label")
def label_tag(key, default=None):
    return _label(key, default=default)


@register.simple_tag(name="message")
def message_tag(key, default=None, **kwargs):
    return _message(key, default=default, **kwargs)
