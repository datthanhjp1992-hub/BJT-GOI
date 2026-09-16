"""
Khu vực quản trị — SC07_QuanTriAdmin.

PHẠM VI (cập nhật 13/09/2026):
1. Bảng TỔNG QUAN — số liệu + người dùng mới nhất.
2. BÁO CÁO LỖI — danh sách báo lỗi người dùng gửi, xem chi tiết, đánh dấu
   đã sửa / bỏ qua kèm phản hồi (model ở apps/error_reports).
3. HÒM THƯ GÓP Ý (SC12) — duyệt/từ chối góp ý người dùng gửi, cộng điểm
   theo PointRule (model + service ở apps/gamification).
4. NHẬP / XUẤT DỮ LIỆU bằng file CSV & Excel cho cả 18 bảng + một mẫu gộp
   "Từ vựng đầy đủ": tải file mẫu, xuất dữ liệu hiện có, chọn chế độ ghi, tải
   file lên và xem trước rồi mới ghi.

Sửa/xoá TỪNG bản ghi vẫn đẩy sang Django admin ở `/admin/` — viết lại form
CRUD từng bảng ở đây là làm lại thứ Django cho không. Cái Django admin làm dở
là nhập hàng loạt từ file, nên chỉ phần đó được viết lại (apps/core/dataio.py).

App này KHÔNG có models.py — nó chỉ đọc/ghi dữ liệu của app khác.
"""
import time
import uuid
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.contrib import messages as django_messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core import dataio

from apps.core.constants import (
    ERROR_STATUS_DISMISSED,
    ERROR_STATUS_FIXED,
    ERROR_STATUS_PENDING,
)
from apps.core.properties import message
from apps.error_reports import services as error_report_services
from apps.error_reports.forms import ErrorReportActionForm
from apps.error_reports.models import ErrorReport
from apps.gamification import services as gamification_services
from apps.gamification.forms import ContributionActionForm
from apps.gamification.models import Contribution
from apps.vocabulary.models import Topic, Vocabulary

User = get_user_model()

# "Chờ duyệt" — xem apps/core/management/commands/seed_mastercode.py,
# code_type 03. Để hằng số ở đây thay vì rải "001" trong truy vấn.
CONTRIBUTION_STATUS_PENDING = "001"

RECENT_USER_LIMIT = 10


def staff_required(view_func):
    """Chỉ cho tài khoản staff vào.

    Chưa đăng nhập -> về trang login (kèm ?next=). Đã đăng nhập mà không phải
    staff -> 403 chứ KHÔNG redirect: người học bấm nhầm link mà bị đá về trang
    đăng nhập sẽ tưởng mình vừa bị đăng xuất.
    """

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied(message("common.error.permission_denied"))
        return view_func(request, *args, **kwargs)

    return _wrapped


def _pending_error_report_count():
    """Số báo lỗi đang chờ xử lý — hiện thành badge cạnh mục "Báo cáo lỗi" trên
    sidebar. Đặt ở đây thay vì context processor để KHÔNG bắt mọi request của
    người học phải chịu thêm 1 câu COUNT chỉ vì admin cần con số đó."""
    return ErrorReport.objects.filter(status_code=ERROR_STATUS_PENDING).count()


@staff_required
def overview_view(request):
    """SC07_QuanTriAdmin — tổng quan hệ thống."""
    stats = {
        "active_users": User.objects.filter(is_active=True).count(),
        "total_vocabulary": Vocabulary.objects.count(),
        "total_topics": Topic.objects.count(),
        "pending_contributions": Contribution.objects.filter(
            status_code=CONTRIBUTION_STATUS_PENDING
        ).count(),
        "unresolved_reports": ErrorReport.objects.filter(
            status_code=ERROR_STATUS_PENDING
        ).count(),
    }
    context = {
        "stats": stats,
        "recent_users": User.objects.order_by("-date_joined")[:RECENT_USER_LIMIT],
        "display_name": (request.user.first_name or "").strip() or request.user.get_username(),
        "active_admin_nav": "overview",
        "pending_error_reports": _pending_error_report_count(),
    }
    return render(request, "admin_panel/overview.html", context)


# ---------------------------------------------------------------------------
# SC07b — Nhập / xuất dữ liệu bằng file CSV & Excel
# ---------------------------------------------------------------------------
# Luồng: tải mẫu -> điền -> chọn chế độ -> tải lên -> XEM TRƯỚC (thêm N / sửa M
# / bỏ qua K / lỗi J) -> bấm xác nhận mới ghi, trong MỘT transaction.
#
# BA CHẾ ĐỘ: chỉ thêm / thêm + cập nhật / chỉ cập nhật (xem apps/core/dataio.py).
# KHÔNG có chế độ xoá — xoá từng dòng vẫn mở ở Django admin, đó là lý do sidebar
# giữ nguyên các link sang /admin/.

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
IMPORT_TMP_DIRNAME = "admin_imports"
IMPORT_SESSION_KEY = "admin_panel_import"
IMPORT_TMP_MAX_AGE_SECONDS = 24 * 60 * 60

CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _import_tmp_dir():
    path = Path(settings.MEDIA_ROOT) / IMPORT_TMP_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _purge_old_uploads():
    """Dọn file tạm quá 1 ngày. Người dùng bỏ ngang ở bước xem trước là chuyện
    thường, không ai đi xoá tay."""
    cutoff = time.time() - IMPORT_TMP_MAX_AGE_SECONDS
    for item in _import_tmp_dir().glob("*"):
        try:
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink()
        except OSError:  # pragma: no cover
            pass


def _resolve_dataset(dataset_label):
    dataset = dataio.get_dataset(dataset_label)
    if dataset is None:
        raise Http404(message("common.error.not_found"))
    return dataset


def _codenames(dataset, action):
    return [
        f"{model._meta.app_label}.{action}_{model._meta.model_name}"
        for model in dataset.perm_models
    ]


def _has_all_perms(request, dataset, action):
    return all(request.user.has_perm(code) for code in _codenames(dataset, action))


def _require_perm(request, dataset, action):
    """staff_required đã chặn người ngoài; ở đây chặn thêm theo quyền từng bảng
    để không phải staff nào cũng nhập được vào mọi bảng.

    Mẫu gộp ghi vào 3 bảng nên phải có quyền trên CẢ BA, không phải chỉ
    vocabulary — nếu không thì quyền trên bảng câu ví dụ thành vô nghĩa.
    """
    if not _has_all_perms(request, dataset, action):
        raise PermissionDenied(message("common.error.permission_denied"))


def _require_mode_perms(request, dataset, mode):
    for action in dataio.MODE_PERMISSIONS[mode]:
        _require_perm(request, dataset, action)


def _available_modes(request, dataset):
    """Chế độ nào thực sự dùng được: có khoá tự nhiên VÀ đủ quyền."""
    modes = []
    for mode in dataio.WRITE_MODES:
        if mode != dataio.MODE_INSERT and not dataset.supports_update():
            continue
        if not all(_has_all_perms(request, dataset, action) for action in dataio.MODE_PERMISSIONS[mode]):
            continue
        modes.append(mode)
    return modes


def _file_response(payload, filename, fmt):
    response = HttpResponse(payload, content_type=CONTENT_TYPES[fmt])
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _table_rows():
    rows = []
    for dataset in dataio.datasets():
        rows.append(
            {
                "label": dataset.label,
                "name": dataset.name,
                "app": dataset.app,
                "count": dataset.count(),
                "columns": len(dataset.columns()),
                "duplicate_key": ", ".join(dataset.natural_key()),
                "is_composite": dataset.is_composite,
                "supports_update": dataset.supports_update(),
            }
        )
    return rows


@staff_required
def data_index_view(request):
    """Danh sách mẫu gộp + 18 bảng, mỗi dòng có lối tải mẫu / xuất / nhập."""
    context = {
        "tables": _table_rows(),
        "active_admin_nav": "data",
        "pending_error_reports": _pending_error_report_count(),
        "max_rows": dataio.MAX_IMPORT_ROWS,
    }
    return render(request, "admin_panel/data_index.html", context)


@staff_required
def data_template_view(request, model_label, fmt):
    """File mẫu: chỉ hàng tiêu đề (+ sheet Huong_dan với bản .xlsx)."""
    dataset = _resolve_dataset(model_label)
    # Tải mẫu để thêm HOẶC để cập nhật — có một trong hai quyền là đủ.
    if not (_has_all_perms(request, dataset, "add") or _has_all_perms(request, dataset, "change")):
        raise PermissionDenied(message("common.error.permission_denied"))
    if fmt not in CONTENT_TYPES:
        raise Http404
    headers = dataset.headers()
    if fmt == "csv":
        payload = dataio.write_csv(headers, [])
    else:
        payload = dataio.write_xlsx(
            headers, [], guide_rows=dataset.guide_rows(), sheet_title=dataset.label.split(".")[-1]
        )
    return _file_response(payload, f"mau_{dataset.label}.{fmt}", fmt)


@staff_required
def data_export_view(request, model_label, fmt):
    """Xuất toàn bộ dữ liệu hiện có, đúng bộ cột của file mẫu.

    File xuất ra nạp lại được ở chế độ "thêm + cập nhật" — đó là cách sửa hàng
    loạt: xuất, sửa trong Excel, nạp lại.
    """
    dataset = _resolve_dataset(model_label)
    _require_perm(request, dataset, "view")
    if fmt not in CONTENT_TYPES:
        raise Http404
    headers = dataset.headers()
    rows = dataset.export_rows()
    if fmt == "csv":
        payload = dataio.write_csv(headers, rows)
    else:
        payload = dataio.write_xlsx(
            headers, rows, guide_rows=dataset.guide_rows(), sheet_title=dataset.label.split(".")[-1]
        )
    stamp = timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M")
    return _file_response(payload, f"{dataset.label}_{stamp}.{fmt}", fmt)


def _import_context(request, dataset, mode, extra=None):
    context = {
        "model_label": dataset.label,
        "model_name": dataset.name,
        "is_composite": dataset.is_composite,
        "columns": dataset.columns(),
        "duplicate_key": ", ".join(dataset.natural_key()),
        "supports_update": dataset.supports_update(),
        "m2m_notes": dataset.m2m_notes(),
        "max_rows": dataio.MAX_IMPORT_ROWS,
        "mode": mode,
        "available_modes": _available_modes(request, dataset),
        "MODE_INSERT": dataio.MODE_INSERT,
        "MODE_UPSERT": dataio.MODE_UPSERT,
        "MODE_UPDATE": dataio.MODE_UPDATE,
        "active_admin_nav": "data",
        "pending_error_reports": _pending_error_report_count(),
    }
    context.update(extra or {})
    return context


def _pick_mode(request, dataset, raw):
    """Chế độ người dùng chọn, đã lọc qua khoá tự nhiên và quyền.

    Không im lặng hạ cấp sang 'chỉ thêm': nếu chọn chế độ không dùng được thì
    báo lỗi, vì âm thầm đổi chế độ ghi là cách chắc chắn nhất để admin tưởng
    mình vừa cập nhật xong trong khi thực tế không có gì đổi.
    """
    mode = dataio.normalize_mode(raw)
    if mode not in _available_modes(request, dataset):
        if mode != dataio.MODE_INSERT and not dataset.supports_update():
            raise dataio.DataFileError("admin.data.error.no_key_for_update")
        raise PermissionDenied(message("common.error.permission_denied"))
    return mode


@staff_required
def data_import_view(request, model_label):
    """Bước 1: chọn chế độ + tải file lên -> xem trước. KHÔNG ghi gì ở bước này."""
    dataset = _resolve_dataset(model_label)
    if not _available_modes(request, dataset):
        raise PermissionDenied(message("common.error.permission_denied"))

    if request.method != "POST":
        default_mode = _available_modes(request, dataset)[0]
        return render(
            request, "admin_panel/data_import.html", _import_context(request, dataset, default_mode)
        )

    try:
        mode = _pick_mode(request, dataset, request.POST.get("mode"))
    except dataio.DataFileError as exc:
        django_messages.error(request, message(exc.message_key, **exc.params))
        return render(
            request,
            "admin_panel/data_import.html",
            _import_context(request, dataset, dataio.MODE_INSERT),
        )

    upload = request.FILES.get("data_file")
    if upload is None:
        django_messages.error(request, message("admin.data.error.no_file"))
        return render(request, "admin_panel/data_import.html", _import_context(request, dataset, mode))
    if upload.size > MAX_UPLOAD_BYTES:
        django_messages.error(
            request,
            message("admin.data.error.file_too_large", max_mb=MAX_UPLOAD_BYTES // (1024 * 1024)),
        )
        return render(request, "admin_panel/data_import.html", _import_context(request, dataset, mode))

    raw = upload.read()
    try:
        headers, rows = dataio.read_table(raw, upload.name)
        report = dataset.analyze(headers, rows, mode=mode)
    except dataio.DataFileError as exc:
        django_messages.error(request, message(exc.message_key, **exc.params))
        return render(request, "admin_panel/data_import.html", _import_context(request, dataset, mode))

    if report.fatal:
        django_messages.error(request, message(report.fatal))

    token = ""
    if report.can_apply:
        _purge_old_uploads()
        suffix = Path(upload.name).suffix.lower()
        token = f"{uuid.uuid4().hex}{suffix}"
        (_import_tmp_dir() / token).write_bytes(raw)
        request.session[IMPORT_SESSION_KEY] = {
            "token": token,
            "model": dataset.label,
            "mode": mode,
            "filename": upload.name,
        }

    return render(
        request,
        "admin_panel/data_import.html",
        _import_context(
            request,
            dataset,
            mode,
            {
                "report": report,
                "token": token,
                "source_filename": upload.name,
                "problem_rows": report.problem_rows[:50],
                "problem_overflow": max(0, report.error_count - 50),
                "preview_rows": report.rows[:50],
                "preview_overflow": max(0, len(report.rows) - 50),
            },
        ),
    )


@staff_required
@require_POST
def data_import_confirm_view(request, model_label):
    """Bước 2: đọc lại chính file đã xem trước rồi ghi, trong 1 transaction.

    Cố tình phân tích LẠI thay vì tin kết quả bước 1: giữa hai bước có thể có
    người khác vừa thêm đúng bản ghi đó. Chế độ ghi lấy từ SESSION chứ không
    lấy từ form — nếu không, sửa một ô hidden là đổi được "chỉ thêm" đã xem
    trước thành "ghi đè".
    """
    dataset = _resolve_dataset(model_label)

    pending = request.session.get(IMPORT_SESSION_KEY) or {}
    token = request.POST.get("token", "")
    if not token or pending.get("token") != token or pending.get("model") != dataset.label:
        django_messages.error(request, message("admin.data.error.session_expired"))
        return redirect("admin_panel:data_import", model_label=dataset.label)

    mode = dataio.normalize_mode(pending.get("mode"))
    _require_mode_perms(request, dataset, mode)

    path = _import_tmp_dir() / token
    if not path.exists():
        django_messages.error(request, message("admin.data.error.session_expired"))
        return redirect("admin_panel:data_import", model_label=dataset.label)

    raw = path.read_bytes()
    try:
        headers, rows = dataio.read_table(raw, pending.get("filename") or token)
        report = dataset.analyze(headers, rows, mode=mode)
        if not report.can_apply:
            django_messages.error(request, message("admin.data.error.changed_since_preview"))
            return redirect("admin_panel:data_import", model_label=dataset.label)
        with transaction.atomic():
            result = dataset.apply(report)
    except dataio.DataFileError as exc:
        django_messages.error(request, message(exc.message_key, **exc.params))
        return redirect("admin_panel:data_import", model_label=dataset.label)
    except IntegrityError as exc:
        django_messages.error(request, message("admin.data.error.integrity", detail=str(exc)))
        return redirect("admin_panel:data_import", model_label=dataset.label)
    finally:
        request.session.pop(IMPORT_SESSION_KEY, None)
        try:
            path.unlink()
        except OSError:  # pragma: no cover
            pass

    django_messages.success(
        request,
        message(
            "admin.data.success.imported",
            created=result.get("created", 0),
            updated=result.get("updated", 0),
            skipped=report.skipped_count,
            table=dataset.name,
        ),
    )
    if dataset.is_composite:
        django_messages.success(
            request,
            message(
                "admin.data.success.imported_full_vocab",
                topics=result.get("topics_linked", 0),
                examples=result.get("examples_added", 0),
            ),
        )
    return redirect("admin_panel:data_index")


# ---------------------------------------------------------------------------
# SC14 — Báo cáo lỗi
# ---------------------------------------------------------------------------
# Một màn duy nhất, bố cục 2 cột như mockup SC12: trái là danh sách lọc theo
# trạng thái, phải là chi tiết bản ghi đang chọn (?selected=<pk>). Không tách
# thành 2 URL để admin duyệt liên tiếp nhiều báo lỗi mà không mất bộ lọc.
#
# Model/luồng trạng thái nằm ở apps/error_reports — view này chỉ điều phối.

ERROR_REPORT_PAGE_SIZE = 30

# Giá trị ?status= trên URL -> mã trạng thái thật trong DB. Dùng chữ trên URL
# (?status=pending) thay vì mã ("001") để link còn đọc được và không lộ mã nội
# bộ; "all" = không lọc.
ERROR_REPORT_FILTERS = {
    "pending": ERROR_STATUS_PENDING,
    "fixed": ERROR_STATUS_FIXED,
    "dismissed": ERROR_STATUS_DISMISSED,
    "all": None,
}
ERROR_REPORT_DEFAULT_FILTER = "pending"


@staff_required
def error_report_list_view(request):
    """Danh sách báo lỗi + chi tiết bản ghi đang chọn."""
    status_key = request.GET.get("status") or ERROR_REPORT_DEFAULT_FILTER
    if status_key not in ERROR_REPORT_FILTERS:
        status_key = ERROR_REPORT_DEFAULT_FILTER
    status_code = ERROR_REPORT_FILTERS[status_key]

    reports = ErrorReport.objects.select_related("user", "vocabulary", "handled_by")
    if status_code:
        reports = reports.filter(status_code=status_code)

    page = Paginator(reports, ERROR_REPORT_PAGE_SIZE).get_page(request.GET.get("page"))

    # Bản ghi đang mở ở cột phải: ?selected=<pk>, mặc định là dòng đầu trang.
    selected = None
    selected_pk = request.GET.get("selected")
    if selected_pk:
        selected = next((r for r in page.object_list if str(r.pk) == str(selected_pk)), None)
        if selected is None:
            # Bấm từ trang khác / bản ghi vừa đổi trạng thái nên rơi khỏi bộ lọc
            # hiện tại — vẫn mở chi tiết thay vì im lặng bỏ qua.
            selected = (
                ErrorReport.objects.select_related("user", "vocabulary", "handled_by")
                .filter(pk=selected_pk)
                .first()
            )
    if selected is None and page.object_list:
        selected = page.object_list[0]

    counts = {
        "pending": ErrorReport.objects.filter(status_code=ERROR_STATUS_PENDING).count(),
        "fixed": ErrorReport.objects.filter(status_code=ERROR_STATUS_FIXED).count(),
        "dismissed": ErrorReport.objects.filter(status_code=ERROR_STATUS_DISMISSED).count(),
    }
    counts["all"] = ErrorReport.objects.count()

    context = {
        "page_obj": page,
        "reports": page.object_list,
        "selected": selected,
        "status_key": status_key,
        "counts": counts,
        "active_admin_nav": "error_reports",
        "pending_error_reports": _pending_error_report_count(),
    }
    return render(request, "admin_panel/error_report_list.html", context)


@staff_required
@require_POST
def error_report_action_view(request, pk):
    """Xử lý một báo lỗi: đã sửa / bỏ qua / mở lại.

    Luôn redirect về đúng bộ lọc + bản ghi vừa thao tác, để admin không bị đá
    về đầu danh sách sau mỗi lần bấm.
    """
    report = ErrorReport.objects.filter(pk=pk).first()
    if report is None:
        raise Http404

    form = ErrorReportActionForm(request.POST)
    status_key = request.POST.get("status") or ERROR_REPORT_DEFAULT_FILTER
    if status_key not in ERROR_REPORT_FILTERS:
        status_key = ERROR_REPORT_DEFAULT_FILTER
    back = f"{reverse('admin_panel:error_report_list')}?status={status_key}&selected={report.pk}"

    if not form.is_valid():
        django_messages.error(request, message("error_report.action.error.invalid"))
        return redirect(back)

    action = form.cleaned_data["action"]
    response_text = form.cleaned_data.get("admin_response", "")
    try:
        if action == ErrorReportActionForm.ACTION_FIX:
            error_report_services.mark_fixed(report, request.user, response_text)
            django_messages.success(request, message("error_report.action.success.fixed"))
        elif action == ErrorReportActionForm.ACTION_DISMISS:
            error_report_services.dismiss(report, request.user, response_text)
            django_messages.success(request, message("error_report.action.success.dismissed"))
        else:
            error_report_services.reopen(report, request.user)
            django_messages.success(request, message("error_report.action.success.reopened"))
    except error_report_services.ErrorReportActionError as exc:
        django_messages.error(request, str(exc))

    return redirect(back)


# ---------------------------------------------------------------------------
# SC12 — Hòm thư góp ý
# ---------------------------------------------------------------------------
# Cùng khuôn với màn Báo cáo lỗi ở trên (danh sách trái · chi tiết phải, lọc
# bằng link) — hai màn cố ý giống nhau để admin không phải học hai cách thao
# tác. Khác ở phần hành động: duyệt góp ý còn GHI vào Vocabulary và CỘNG ĐIỂM,
# nên toàn bộ nằm trong apps/gamification/services.py chứ không viết ở đây.

CONTRIBUTION_PAGE_SIZE = 30

CONTRIBUTION_FILTERS = {
    "pending": gamification_services.STATUS_PENDING,
    "approved": gamification_services.STATUS_APPROVED,
    "rejected": gamification_services.STATUS_REJECTED,
    "all": None,
}
CONTRIBUTION_DEFAULT_FILTER = "pending"


@staff_required
def contribution_inbox_view(request):
    """Danh sách góp ý + chi tiết bản ghi đang chọn."""
    status_key = request.GET.get("status") or CONTRIBUTION_DEFAULT_FILTER
    if status_key not in CONTRIBUTION_FILTERS:
        status_key = CONTRIBUTION_DEFAULT_FILTER
    status_code = CONTRIBUTION_FILTERS[status_key]

    rows = Contribution.objects.select_related("user", "target_vocabulary", "proposed_topic", "reviewed_by")
    if status_code:
        rows = rows.filter(status_code=status_code)

    page = Paginator(rows, CONTRIBUTION_PAGE_SIZE).get_page(request.GET.get("page"))

    selected = None
    selected_pk = request.GET.get("selected")
    if selected_pk:
        selected = next((c for c in page.object_list if str(c.pk) == str(selected_pk)), None)
        if selected is None:
            # Bản ghi vừa đổi trạng thái nên rơi khỏi bộ lọc hiện tại — vẫn mở
            # chi tiết thay vì im lặng bỏ qua.
            selected = (
                Contribution.objects.select_related("user", "target_vocabulary", "proposed_topic", "reviewed_by")
                .filter(pk=selected_pk)
                .first()
            )
    if selected is None and page.object_list:
        selected = page.object_list[0]

    counts = {
        key: (Contribution.objects.count() if code is None
              else Contribution.objects.filter(status_code=code).count())
        for key, code in CONTRIBUTION_FILTERS.items()
    }

    context = {
        "page_obj": page,
        "contributions": page.object_list,
        "selected": selected,
        "status_key": status_key,
        "counts": counts,
        "topics": Topic.objects.all(),
        "type_new_word": gamification_services.CONTRIBUTION_TYPE_NEW_WORD,
        "type_edit_meaning": gamification_services.CONTRIBUTION_TYPE_EDIT_MEANING,
        "type_comment": gamification_services.CONTRIBUTION_TYPE_COMMENT,
        "active_admin_nav": "contributions",
        "pending_error_reports": _pending_error_report_count(),
    }
    return render(request, "admin_panel/contribution_inbox.html", context)


@staff_required
@require_POST
def contribution_action_view(request, pk):
    """Duyệt / từ chối một góp ý.

    Admin được sửa lại nội dung đề xuất trước khi duyệt (mockup SC12): các ô
    đó ghi đè `proposed_*` TRƯỚC khi gọi service, nên dữ liệu vào Vocabulary
    đúng bằng những gì admin nhìn thấy trên màn hình.
    """
    contribution = Contribution.objects.filter(pk=pk).first()
    if contribution is None:
        raise Http404

    status_key = request.POST.get("status") or CONTRIBUTION_DEFAULT_FILTER
    if status_key not in CONTRIBUTION_FILTERS:
        status_key = CONTRIBUTION_DEFAULT_FILTER
    back = f"{reverse('admin_panel:contribution_inbox')}?status={status_key}&selected={contribution.pk}"

    if contribution.status_code != gamification_services.STATUS_PENDING:
        django_messages.error(request, message("contribution.action.error.already_reviewed"))
        return redirect(back)

    form = ContributionActionForm(request.POST)
    if not form.is_valid():
        django_messages.error(request, message("contribution.action.error.invalid"))
        return redirect(back)

    data = form.cleaned_data
    response_text = (data.get("admin_response") or "").strip()

    if data["action"] == ContributionActionForm.ACTION_REJECT:
        try:
            gamification_services.reject_contribution(contribution, request.user, response_text)
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect(back)
        django_messages.success(request, message("contribution.reject.success"))
        return redirect(back)

    # --- Duyệt ---
    if contribution.contribution_type_code == gamification_services.CONTRIBUTION_TYPE_NEW_WORD:
        contribution.proposed_word = (data.get("word") or contribution.proposed_word).strip()
        contribution.proposed_reading = (data.get("reading") or contribution.proposed_reading).strip()
        contribution.proposed_meaning_vi = (data.get("meaning_vi") or contribution.proposed_meaning_vi).strip()
        if data.get("topic"):
            contribution.proposed_topic = data["topic"]
        if not (contribution.proposed_word and contribution.proposed_reading and contribution.proposed_meaning_vi):
            django_messages.error(request, message("contribution.approve.error.missing_required_field"))
            return redirect(back)

    elif contribution.contribution_type_code == gamification_services.CONTRIBUTION_TYPE_EDIT_MEANING:
        if data.get("meaning_vi"):
            contribution.proposed_meaning_vi = data["meaning_vi"].strip()
        if data.get("reading"):
            contribution.proposed_reading = data["reading"].strip()
        if contribution.target_vocabulary is None:
            # Từ đích đã bị xoá (FK là SET_NULL) — duyệt sẽ không có gì để ghi.
            django_messages.error(request, message("contribution.approve.error.target_gone"))
            return redirect(back)

    gamification_services.approve_contribution(contribution, request.user, response_text)
    django_messages.success(
        request, message("contribution.approve.success", points=contribution.points_awarded)
    )
    return redirect(back)
