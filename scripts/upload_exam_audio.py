"""
Upload audio đề thi lên Supabase Storage, bucket public "exam-audio" — docs/SPEC_KIEM_TRA.md T7.3.

    # 1. chạy thử — so file trên máy với bucket, in kế hoạch, KHÔNG upload (mặc định)
    python scripts/upload_exam_audio.py ../BJT-WEB/media/audio/mock_exam

    # 2. upload thật
    python scripts/upload_exam_audio.py ../BJT-WEB/media/audio/mock_exam --apply --as-user dat

Từng file .mp3 trong thư mục -> object <prefix><tên file> (mặc định prefix "mock/", khớp
audio_path do scripts/export_bjt_exam.py ghi). So theo MD5 nội dung với eTag của object:
  - chưa có trên bucket       -> upload mới
  - có nhưng nội dung khác    -> GHI ĐÈ + tăng ExamQuestion.audio_version của các câu dùng
                                 file đó (URL đổi ?v= -> người học nghe bản mới ngay)
  - giống hệt                 -> bỏ qua
Object trên bucket không còn file nào tương ứng chỉ được BÁO, không tự xoá.

Cần trong .env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (khoá secret — chỉ ở máy local).
Phải chạy SAU scripts/import_exam.py (cần bảng exam_examquestion trên DB để tăng phiên bản).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

from _vocab_common import DIM, GREEN, RED, RESET, YELLOW, act_as, say, setup_django

BUCKET = "exam-audio"
CACHE_CONTROL = "max-age=31536000"  # an toàn vì URL đổi ?v= mỗi lần ghi đè
LIST_PAGE = 1000


def _headers(key, extra=None):
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    h.update(extra or {})
    return h


def list_remote(base, key, prefix):
    """{đường dẫn: eTag} của mọi object dưới prefix."""
    folder = prefix.rstrip("/")
    out, offset = {}, 0
    while True:
        body = json.dumps({"prefix": folder, "limit": LIST_PAGE, "offset": offset,
                           "sortBy": {"column": "name", "order": "asc"}}).encode()
        req = urllib.request.Request(f"{base}/storage/v1/object/list/{BUCKET}", data=body, method="POST",
                                     headers=_headers(key, {"Content-Type": "application/json"}))
        with urllib.request.urlopen(req, timeout=30) as r:
            items = json.loads(r.read())
        for item in items:
            if item.get("id") is None:  # thư mục con, không phải file
                continue
            path = f"{folder}/{item['name']}" if folder else item["name"]
            out[path] = (item.get("metadata") or {}).get("eTag", "")
        if len(items) < LIST_PAGE:
            return out
        offset += LIST_PAGE


def upload(base, key, path, file_path, overwrite):
    req = urllib.request.Request(
        f"{base}/storage/v1/object/{BUCKET}/{quote(path)}", data=Path(file_path).read_bytes(), method="POST",
        headers=_headers(key, {"Content-Type": "audio/mpeg", "cache-control": CACHE_CONTROL,
                               "x-upsert": "true" if overwrite else "false"}),
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()


def main():
    ap = argparse.ArgumentParser(description="Upload audio đề thi lên Supabase Storage.")
    ap.add_argument("folder", type=Path, help="Thư mục chứa file .mp3")
    ap.add_argument("--prefix", default="mock/", help='Thư mục trong bucket (mặc định "mock/").')
    ap.add_argument("--apply", action="store_true", help="Upload thật. Không có cờ này thì chỉ chạy thử.")
    ap.add_argument("--as-user", metavar="USERNAME", help="Ghi updated_by khi tăng audio_version.")
    ap.add_argument("--settings", default="config.settings.supabase", help="DJANGO_SETTINGS_MODULE.")
    args = ap.parse_args()

    if not args.folder.is_dir():
        say(RED, "LỖI", f"Không thấy thư mục {args.folder}")
        sys.exit(1)
    setup_django(args.settings)  # nạp .env
    from django.db.models import F

    from apps.core import middleware
    from apps.exam.audio import UPLOAD_NEW, UPLOAD_OVERWRITE, UPLOAD_SAME, md5_of, plan_uploads
    from apps.exam.models import ExamQuestion

    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key:
        say(RED, "LỖI", "Thiếu SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY trong .env (xem .env.example).")
        sys.exit(1)
    say(YELLOW if args.apply else GREEN, "MODE", "UPLOAD THẬT" if args.apply else "CHẠY THỬ (không upload)")

    prefix = args.prefix if args.prefix.endswith("/") else args.prefix + "/"
    files = {prefix + p.name: p for p in sorted(args.folder.glob("*.mp3"))}
    local = {path: md5_of(p) for path, p in files.items()}
    try:
        remote = list_remote(base, key, prefix)
    except urllib.error.HTTPError as e:
        say(RED, "LỖI", f"Không đọc được bucket {BUCKET}: HTTP {e.code} {e.read()[:200]!r}")
        sys.exit(1)
    plan, orphans = plan_uploads(local, remote)

    used = set(ExamQuestion.objects.exclude(audio_path="").values_list("audio_path", flat=True))
    unused_local = sorted(set(local) - used)
    missing_local = sorted(used - set(local))

    counts = {UPLOAD_NEW: 0, UPLOAD_OVERWRITE: 0, UPLOAD_SAME: 0}
    for path, action in plan:
        counts[action] += 1
        if action != UPLOAD_SAME:
            say(GREEN if action == UPLOAD_NEW else YELLOW, f"  {action:>9}", path)

    failed = []
    if args.apply:
        act_as(args.as_user)
        try:
            for path, action in plan:
                if action == UPLOAD_SAME:
                    continue
                try:
                    upload(base, key, path, files[path], overwrite=action == UPLOAD_OVERWRITE)
                except urllib.error.HTTPError as e:
                    failed.append(f"{path}: HTTP {e.code} {e.read()[:200]!r}")
                    continue
                if action == UPLOAD_OVERWRITE:
                    # update() không qua save() -> tự đặt updated_at; ghi nhận ngay sau
                    # khi file lên bucket để URL đổi đúng lúc nội dung đổi.
                    for q in ExamQuestion.objects.filter(audio_path=path):
                        q.audio_version = F("audio_version") + 1
                        q.save(update_fields=["audio_version", "updated_at", "updated_by"])
        finally:
            middleware._thread_locals.user = None

    print()
    print(f"  File trên máy : {len(local)}  ·  object trên bucket ({prefix}): {len(remote)}")
    print(f"  Upload mới    : {counts[UPLOAD_NEW]}")
    print(f"  Ghi đè        : {counts[UPLOAD_OVERWRITE]}  (tăng audio_version các câu dùng file)")
    print(f"  Giữ nguyên    : {counts[UPLOAD_SAME]}")
    if failed:
        print(f"{RED}  Lỗi upload    : {len(failed)}{RESET}")
        for f in failed:
            print("     •", f)
    if orphans:
        print(f"{DIM}  Object trên bucket không còn file trên máy (chỉ báo, không xoá): {len(orphans)}{RESET}")
    if unused_local:
        print(f"{DIM}  File trên máy chưa câu nào dùng: {len(unused_local)}{RESET}")
    if missing_local:
        print(f"{RED}  Câu đề trỏ tới file KHÔNG có trong thư mục: {len(missing_local)} (vd {missing_local[0]}){RESET}")
    if not args.apply:
        print(f"\nChạy lại với {YELLOW}--apply{RESET} để upload thật.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
