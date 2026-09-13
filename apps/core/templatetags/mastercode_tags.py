"""
Dùng trong template: {{ contribution.status_code|code_name:"03" }}
thay vì if/elif thủ công để đổi mã trạng thái/loại ra tên hiển thị.
"""
from django import template

from apps.core.mastercode import get_code_name

register = template.Library()


@register.filter(name="code_name")
def code_name(code, code_type):
    return get_code_name(code_type, code, default=code or "")
