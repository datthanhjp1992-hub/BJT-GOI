"""
Nghiệp vụ xử lý báo cáo lỗi — tách khỏi view để admin_panel (và sau này lệnh
quản trị hay API) dùng chung một luồng, không ai tự set `status_code` bằng tay.

Vòng đời:

    Chờ xử lý (001) --admin đánh dấu đã sửa--> Đã sửa (002)
                    --admin bỏ qua----------> Bỏ qua (003)  (bắt buộc ghi lý do)

Không có bước "cộng điểm" như bên góp ý: báo lỗi là báo hỏng, giá trị nằm ở
chỗ lỗi được sửa chứ không phải ở nội dung người dùng đóng góp. Nếu sau này
muốn thưởng điểm cho người báo lỗi đúng, thêm 1 action_code mới ở
CODE_TYPE_POINT_ACTION rồi gọi apps.gamification.services từ `mark_fixed` —
không phải sửa model.
"""
from django.db import transaction
from django.utils import timezone

from apps.core.constants import (
    ERROR_STATUS_DISMISSED,
    ERROR_STATUS_FIXED,
    ERROR_STATUS_PENDING,
)
from apps.core.properties import message


class ErrorReportActionError(Exception):
    """Hành động không hợp lệ — view bắt và đổ ra flash message, không 500."""


def _apply(report, admin_user, status_code, admin_response):
    report.status_code = status_code
    report.admin_response = (admin_response or "").strip()
    report.handled_by = admin_user
    report.handled_at = timezone.now()
    report.save(update_fields=[
        "status_code", "admin_response", "handled_by", "handled_at",
        "updated_by", "updated_at",
    ])
    return report


@transaction.atomic
def mark_fixed(report, admin_user, admin_response=""):
    """Đánh dấu đã sửa. Phản hồi cho người báo là TUỲ CHỌN — bản thân việc lỗi
    được sửa đã là câu trả lời rồi."""
    if not report.is_pending:
        raise ErrorReportActionError(message("error_report.action.error.already_handled"))
    return _apply(report, admin_user, ERROR_STATUS_FIXED, admin_response)


@transaction.atomic
def dismiss(report, admin_user, admin_response=""):
    """Bỏ qua. BẮT BUỘC ghi lý do: người dùng bỏ công báo lỗi mà nhận về một ô
    trống thì lần sau không báo nữa."""
    if not report.is_pending:
        raise ErrorReportActionError(message("error_report.action.error.already_handled"))
    if not (admin_response or "").strip():
        raise ErrorReportActionError(message("error_report.action.error.reason_required"))
    return _apply(report, admin_user, ERROR_STATUS_DISMISSED, admin_response)


@transaction.atomic
def reopen(report, admin_user):
    """Mở lại một báo lỗi đã xử lý (bấm nhầm, hoặc lỗi tái phát)."""
    if report.is_pending:
        raise ErrorReportActionError(message("error_report.action.error.already_pending"))
    report.status_code = ERROR_STATUS_PENDING
    report.handled_by = None
    report.handled_at = None
    report.save(update_fields=[
        "status_code", "handled_by", "handled_at", "updated_by", "updated_at",
    ])
    return report
