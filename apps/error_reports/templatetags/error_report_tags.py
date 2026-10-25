"""
{% report_inline vocabulary_id=... %} / {% report_inline exam_question_id=... %}

Nút "🚩 Báo lỗi" mở form ngay tại chỗ (thay cho link sang /error-reports/new/):
gửi xong người học vẫn ở nguyên màn đang học/đang thi. main.js gửi form bằng
fetch; tắt JS thì form vẫn gửi thường về report_create_view.
"""
from django import template

from apps.error_reports.forms import ErrorReportForm

register = template.Library()


@register.inclusion_tag("error_reports/_inline.html", takes_context=True)
def report_inline(context, vocabulary_id=None, exam_question_id=None):
    return {
        "form": ErrorReportForm(auto_id=False),
        "vocabulary_id": vocabulary_id,
        "exam_question_id": exam_question_id,
        "csrf_token": context.get("csrf_token"),
    }
