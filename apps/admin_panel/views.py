"""
Khu vực quản trị — SC07_QuanTriAdmin.

PHẠM VI (cập nhật 13/09/2026):
1. Bảng TỔNG QUAN — số liệu + người dùng mới nhất.
2. NHẬP / XUẤT DỮ LIỆU bằng file CSV & Excel cho cả 18 bảng: tải file mẫu,
   xuất dữ liệu hiện có, tải file lên và xem trước rồi mới ghi.

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
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core import dataio

from apps.core.properties import message
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
    }
    context = {
        "stats": stats,
        "recent_users": User.objects.order_by("-date_joined")[:RECENT_USER_LIMIT],
        "display_name": (request.user.first_name or "").strip() or request.user.get_username(),
        "active_admin_nav": "overview",
    }
    return render(request, "admin_panel/overview.html", context)


# ---------------------------------------------------------------------------
# SC07b — Nhập / xuất dữ liệu bằng file CSV & Excel
# ---------------------------------------------------------------------------
# Luồng: tải mẫu -> điền -> tải lên -> XEM TRƯỚC (thêm N / trùng M / lỗi K)
# -> bấm xác nhận mới ghi, trong MỘT transaction.
#
# Chỉ THÊM MỚI. Dòng đã có (so theo khoá tự nhiên, xem apps/core/dataio.py) bị
# bỏ qua; không sửa, không xoá bản ghi nào. Sửa/xoá từng dòng vẫn mở ở Django
# admin — đó là lý do sidebar giữ nguyên các link sang /admin/.

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


def _resolve_model(model_label):
    model = dataio.get_importable_model(model_label)
    if model is None:
        raise Http404(message("common.error.not_found"))
    return model


def _require_perm(request, model, action):
    """staff_required đã chặn người ngoài; ở đây chặn thêm theo quyền từng bảng
    để không phải staff nào cũng nhập được vào mọi bảng."""
    codename = f"{model._meta.app_label}.{action}_{model._meta.model_name}"
    if not request.user.has_perm(codename):
        raise PermissionDenied(message("common.error.permission_denied"))


def _file_response(payload, filename, fmt):
    response = HttpResponse(payload, content_type=CONTENT_TYPES[fmt])
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _table_rows():
    rows = []
    for model in dataio.importable_models():
        rows.append(
            {
                "label": dataio.model_label(model),
                "name": dataio.verbose_name(model),
                "app": model._meta.app_label,
                "count": model._default_manager.count(),
                "columns": len(dataio.columns_for(model)),
                "duplicate_key": ", ".join(dataio.duplicate_fields(model)),
            }
        )
    return rows


@staff_required
def data_index_view(request):
    """Danh sách 18 bảng + lối vào tải mẫu / xuất / nhập."""
    context = {
        "tables": _table_rows(),
        "active_admin_nav": "data",
        "max_rows": dataio.MAX_IMPORT_ROWS,
    }
    return render(request, "admin_panel/data_index.html", context)


@staff_required
def data_template_view(request, model_label, fmt):
    """File mẫu: chỉ hàng tiêu đề (+ sheet Huong_dan với bản .xlsx)."""
    model = _resolve_model(model_label)
    _require_perm(request, model, "add")
    if fmt not in CONTENT_TYPES:
        raise Http404
    headers = dataio.headers_for(model)
    if fmt == "csv":
        payload = dataio.write_csv(headers, [])
    else:
        payload = dataio.write_xlsx(
            headers, [], guide_rows=dataio.guide_rows(model), sheet_title=model._meta.model_name
        )
    return _file_response(payload, f"mau_{model_label}.{fmt}", fmt)


@staff_required
def data_export_view(request, model_label, fmt):
    """Xuất toàn bộ dữ liệu hiện có, đúng bộ cột của file mẫu."""
    model = _resolve_model(model_label)
    _require_perm(request, model, "view")
    if fmt not in CONTENT_TYPES:
        raise Http404
    headers = dataio.headers_for(model)
    rows = dataio.export_rows(model)
    if fmt == "csv":
        payload = dataio.write_csv(headers, rows)
    else:
        payload = dataio.write_xlsx(
            headers, rows, guide_rows=dataio.guide_rows(model), sheet_title=model._meta.model_name
        )
    stamp = timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M")
    return _file_response(payload, f"{model_label}_{stamp}.{fmt}", fmt)


def _import_context(model, extra=None):
    context = {
        "model_label": dataio.model_label(model),
        "model_name": dataio.verbose_name(model),
        "columns": dataio.columns_for(model),
        "duplicate_key": ", ".join(dataio.duplicate_fields(model)),
        "m2m_notes": dataio.skipped_m2m_names(model),
        "max_rows": dataio.MAX_IMPORT_ROWS,
        "active_admin_nav": "data",
    }
    context.update(extra or {})
    return context


@staff_required
def data_import_view(request, model_label):
    """Bước 1: tải file lên -> xem trước. KHÔNG ghi gì ở bước này."""
    model = _resolve_model(model_label)
    _require_perm(request, model, "add")

    if request.method != "POST":
        return render(request, "admin_panel/data_import.html", _import_context(model))

    upload = request.FILES.get("data_file")
    if upload is None:
        django_messages.error(request, message("admin.data.error.no_file"))
        return render(request, "admin_panel/data_import.html", _import_context(model))
    if upload.size > MAX_UPLOAD_BYTES:
        django_messages.error(
            request,
            message("admin.data.error.file_too_large", max_mb=MAX_UPLOAD_BYTES // (1024 * 1024)),
        )
        return render(request, "admin_panel/data_import.html", _import_context(model))

    raw = upload.read()
    try:
        headers, rows = dataio.read_table(raw, upload.name)
        report = dataio.analyze(model, headers, rows)
    except dataio.DataFileError as exc:
        django_messages.error(request, message(exc.message_key, **exc.params))
        return render(request, "admin_panel/data_import.html", _import_context(model))

    token = ""
    if report.can_apply:
        _purge_old_uploads()
        suffix = Path(upload.name).suffix.lower()
        token = f"{uuid.uuid4().hex}{suffix}"
        (_import_tmp_dir() / token).write_bytes(raw)
        request.session[IMPORT_SESSION_KEY] = {
            "token": token,
            "model": dataio.model_label(model),
            "filename": upload.name,
        }

    return render(
        request,
        "admin_panel/data_import.html",
        _import_context(
            model,
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
    người khác vừa thêm đúng bản ghi đó.
    """
    model = _resolve_model(model_label)
    _require_perm(request, model, "add")

    pending = request.session.get(IMPORT_SESSION_KEY) or {}
    token = request.POST.get("token", "")
    if not token or pending.get("token") != token or pending.get("model") != dataio.model_label(model):
        django_messages.error(request, message("admin.data.error.session_expired"))
        return redirect("admin_panel:data_import", model_label=dataio.model_label(model))

    path = _import_tmp_dir() / token
    if not path.exists():
        django_messages.error(request, message("admin.data.error.session_expired"))
        return redirect("admin_panel:data_import", model_label=dataio.model_label(model))

    raw = path.read_bytes()
    try:
        headers, rows = dataio.read_table(raw, pending.get("filename") or token)
        report = dataio.analyze(model, headers, rows)
        if not report.can_apply:
            django_messages.error(request, message("admin.data.error.changed_since_preview"))
            return redirect("admin_panel:data_import", model_label=dataio.model_label(model))
        with transaction.atomic():
            created = dataio.apply_report(report, model)
    except dataio.DataFileError as exc:
        django_messages.error(request, message(exc.message_key, **exc.params))
        return redirect("admin_panel:data_import", model_label=dataio.model_label(model))
    except IntegrityError as exc:
        django_messages.error(request, message("admin.data.error.integrity", detail=str(exc)))
        return redirect("admin_panel:data_import", model_label=dataio.model_label(model))
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
            created=created,
            skipped=report.duplicate_count,
            table=dataio.verbose_name(model),
        ),
    )
    return redirect("admin_panel:data_index")
