"""
View phía NGƯỜI HỌC của tính năng báo cáo lỗi (SC14):

    /error-reports/          -> "Báo lỗi của tôi": lịch sử + phản hồi của admin
    /error-reports/new/      -> form gửi báo lỗi (kèm ?vocabulary=<id> nếu báo
                                lỗi một từ cụ thể)

Phía ADMIN nằm ở apps/admin_panel/views.py — đúng quy ước của dự án: mọi màn
trong khu quản trị dùng chung sidebar + decorator staff_required ở đó, app này
chỉ giữ model/form/service.
"""
from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.properties import message
from apps.vocabulary.models import Vocabulary

from .forms import ErrorReportForm
from .models import ErrorReport

PAGE_SIZE = 20
VOCABULARY_PARAM = "vocabulary"


def _referer_path(request):
    """Đường dẫn trang người dùng đang đứng khi bấm "Báo lỗi".

    Chỉ giữ phần path (bỏ scheme/host) và cắt cho vừa cột — dữ liệu này chỉ để
    admin lần lại hiện trường, KHÔNG bao giờ dùng để redirect.
    """
    referer = request.META.get("HTTP_REFERER") or ""
    if not referer:
        return ""
    path = referer.split("://", 1)[-1]
    path = path[path.find("/"):] if "/" in path else ""
    return path[:255]


@login_required
def report_create_view(request):
    """Gửi một báo lỗi mới."""
    vocabulary = None
    vocabulary_id = request.POST.get(VOCABULARY_PARAM) or request.GET.get(VOCABULARY_PARAM)
    if vocabulary_id:
        # Id rác trên query string thì lờ đi (người dùng sửa URL bằng tay không
        # đáng nhận trang lỗi) — form vẫn gửi được dưới dạng báo lỗi chung.
        vocabulary = Vocabulary.objects.filter(pk=vocabulary_id).first()

    if request.method == "POST":
        form = ErrorReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.user = request.user
            report.vocabulary = vocabulary
            report.page_path = _referer_path(request)
            report.save()
            flash.success(request, message("error_report.create.success"))
            return redirect("error_reports:mine")
    else:
        form = ErrorReportForm()

    context = {
        "form": form,
        "vocabulary": vocabulary,
        "active_nav": "vocabulary",
    }
    return render(request, "error_reports/form.html", context)


@login_required
def my_reports_view(request):
    """Lịch sử báo lỗi của chính người đang đăng nhập + phản hồi admin."""
    reports = (
        ErrorReport.objects.filter(user=request.user)
        .select_related("vocabulary", "handled_by")
    )
    page = Paginator(reports, PAGE_SIZE).get_page(request.GET.get("page"))
    context = {
        "page_obj": page,
        "total_count": page.paginator.count,
        "active_nav": "vocabulary",
    }
    return render(request, "error_reports/mine.html", context)
