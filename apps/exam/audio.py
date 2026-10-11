"""
URL audio đề thi — MỘT chỗ duy nhất dựng URL (docs/SPEC_KIEM_TRA.md mục 0.3).

    EXAM_AUDIO_BASE_URL + audio_path + ?v=<audio_version>

?v= đổi mỗi lần scripts/upload_exam_audio.py ghi đè file, nên CDN Supabase và
trình duyệt luôn tải bản mới dù đặt cache dài. Đổi nơi lưu về sau chỉ sửa hàm này.
"""
from urllib.parse import quote

from django.conf import settings


def exam_audio_url(question):
    """"" nếu câu không có audio hoặc chưa cấu hình EXAM_AUDIO_BASE_URL."""
    base = (getattr(settings, "EXAM_AUDIO_BASE_URL", "") or "").strip()
    path = (getattr(question, "audio_path", "") or "").strip().lstrip("/")
    if not base or not path:
        return ""
    if not base.endswith("/"):
        base += "/"
    return f"{base}{quote(path)}?v={int(getattr(question, 'audio_version', 1) or 1)}"


# =============================================================================
# Kế hoạch upload (scripts/upload_exam_audio.py) — hàm thuần, test không cần mạng
# =============================================================================
UPLOAD_NEW = "new"
UPLOAD_OVERWRITE = "overwrite"
UPLOAD_SAME = "same"


def md5_of(path):
    import hashlib

    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def plan_uploads(local, remote):
    """So file trên máy với object trên bucket.

    local : {đường dẫn trong bucket: md5}
    remote: {đường dẫn trong bucket: eTag}  — eTag của Supabase/S3 là md5 nội dung (có
            thể kèm dấu nháy) với file upload một lần; audio ~57 KB nên luôn như vậy.
    Trả về (list (path, action) theo thứ tự tên, list path chỉ có trên bucket).
    """
    def clean(etag):
        return (etag or "").strip().strip('"').lower()

    plan = []
    for path in sorted(local):
        if path not in remote:
            plan.append((path, UPLOAD_NEW))
        elif clean(remote[path]) != local[path].lower():
            plan.append((path, UPLOAD_OVERWRITE))
        else:
            plan.append((path, UPLOAD_SAME))
    orphans = sorted(set(remote) - set(local))
    return plan, orphans
