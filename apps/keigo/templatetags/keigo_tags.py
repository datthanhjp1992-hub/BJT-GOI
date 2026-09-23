"""Template filter cho cú pháp ruby (furigana) của dữ liệu kính ngữ.

Dữ liệu lưu ruby bằng MỘT cột duy nhất, cú pháp `{漢字|かんじ}`:

    "{芥川賞|あくたがわしょう}受賞、おめでとうございます。"

Vì sao không phải hai cột `text` + `text_with_ruby`: hai cột luôn lệch nhau sau
vài lần đính chính, và file Excel nhập liệu sẽ có hai cột gần như trùng nhau —
người nhập chắc chắn sẽ sửa một cột và quên cột kia.
"""
import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

# Không cho { } | lọt vào trong hai nhóm -> không có chuyện lồng nhau hay ăn
# tham lam qua nhiều cặp ngoặc liền kề ({由|よし}{承|うけたまわ}り).
RUBY_RE = re.compile(r"\{([^{}|]+)\|([^{}|]+)\}")


@register.filter(name="ruby")
def ruby(value):
    """`{漢字|かんじ}` -> `<ruby>漢字<rt>かんじ</rt></ruby>`.

    escape() chạy TRƯỚC khi ghép thẻ — nếu mark_safe trước thì mọi chuỗi người
    nhập gõ vào màn quản trị dữ liệu đều chạy thẳng vào trang như HTML. Dấu
    `{ } |` không nằm trong bộ ký tự bị escape nên regex vẫn khớp sau khi escape.
    """
    if value is None:
        return ""
    text = escape(str(value))
    return mark_safe(RUBY_RE.sub(r"<ruby>\1<rt>\2</rt></ruby>", text))


@register.filter(name="strip_ruby")
def strip_ruby(value):
    """Bỏ phần phiên âm, giữ lại mặt chữ — dùng cho tiêu đề, thẻ title, PDF,
    hay bất kỳ chỗ nào không dựng được thẻ <ruby>. Trả về chuỗi THƯỜNG (không
    mark_safe) để nơi gọi tự escape theo ngữ cảnh của nó."""
    if value is None:
        return ""
    return RUBY_RE.sub(r"\1", str(value))
