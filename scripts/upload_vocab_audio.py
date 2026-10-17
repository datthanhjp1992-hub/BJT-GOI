"""
Upload audio từ vựng + câu ví dụ (do scripts/generate_vocab_audio.py tạo) lên Supabase Storage,
bucket public "vocab-audio", rồi ghi Vocabulary.audio_url / ExampleSentence.audio_url.

    # 1. chạy thử — so file trên máy với bucket + DB, in kế hoạch, KHÔNG ghi gì (mặc định)
    python scripts/upload_vocab_audio.py

    # 2. chạy thật (tạo bucket nếu chưa có, upload, ghi audio_url)
    python scripts/upload_vocab_audio.py --apply --as-user dat

w<id>.mp3 -> Vocabulary id, e<id>.mp3 -> ExampleSentence id. So MD5 với eTag trên bucket:
chưa có -> upload, khác -> ghi đè, giống -> bỏ qua. URL kèm ?v=<md5 rút gọn> nên sửa câu +
tạo lại audio thì URL tự đổi. Object trên bucket không còn file trên máy chỉ được BÁO, không xoá.

Cần: .env có SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY; DB đã migrate tới
vocabulary.0007_examplesentence_audio_url (python manage.py migrate --settings=config.settings.supabase).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from _vocab_common import BASE_DIR, DIM, GREEN, RED, RESET, YELLOW, act_as, say, setup_django
from upload_exam_audio import _headers

CACHE_CONTROL = "max-age=31536000"  # an toàn vì URL đổi ?v= khi nội dung đổi
LIST_PAGE = 1000
WORKERS = 8


def bucket_exists(base, key, bucket):
    # object/list trả [] cả khi bucket chưa có, nên phải hỏi riêng.
    req = urllib.request.Request(f"{base}/storage/v1/bucket/{bucket}", headers=_headers(key))
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        return True
    except urllib.error.HTTPError as e:
        if b"not found" in e.read().lower():
            return False
        raise


def list_remote(base, key, bucket):
    """{tên file: eTag} ở gốc bucket."""
    out, offset = {}, 0
    while True:
        body = json.dumps({"prefix": "", "limit": LIST_PAGE, "offset": offset,
                           "sortBy": {"column": "name", "order": "asc"}}).encode()
        req = urllib.request.Request(f"{base}/storage/v1/object/list/{bucket}", data=body, method="POST",
                                     headers=_headers(key, {"Content-Type": "application/json"}))
        with urllib.request.urlopen(req, timeout=30) as r:
            items = json.loads(r.read())
        for item in items:
            if item.get("id") is not None:  # bỏ thư mục con
                out[item["name"]] = (item.get("metadata") or {}).get("eTag", "")
        if len(items) < LIST_PAGE:
            return out
        offset += LIST_PAGE


def create_bucket(base, key, bucket):
    body = json.dumps({"id": bucket, "name": bucket, "public": True}).encode()
    req = urllib.request.Request(f"{base}/storage/v1/bucket", data=body, method="POST",
                                 headers=_headers(key, {"Content-Type": "application/json"}))
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def upload(base, key, bucket, name, file_path, overwrite):
    req = urllib.request.Request(
        f"{base}/storage/v1/object/{bucket}/{name}", data=Path(file_path).read_bytes(), method="POST",
        headers=_headers(key, {"Content-Type": "audio/mpeg", "cache-control": CACHE_CONTROL,
                               "x-upsert": "true" if overwrite else "false"}),
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()


def main():
    ap = argparse.ArgumentParser(description="Upload audio từ vựng lên Supabase + ghi audio_url.")
    ap.add_argument("folder", type=Path, nargs="?", default=BASE_DIR / "media" / "vocab_audio")
    ap.add_argument("--apply", action="store_true", help="Ghi thật. Không có cờ này thì chỉ chạy thử.")
    ap.add_argument("--as-user", metavar="USERNAME", help="Ghi updated_by cho các dòng đổi audio_url.")
    ap.add_argument("--settings", default="config.settings.supabase", help="DJANGO_SETTINGS_MODULE.")
    args = ap.parse_args()

    if not args.folder.is_dir():
        say(RED, "LỖI", f"Không thấy thư mục {args.folder}")
        sys.exit(1)
    setup_django(args.settings)  # nạp .env
    from django.db import connection, transaction
    from django.utils import timezone

    from apps.core import middleware
    from apps.core.middleware import get_current_user
    from apps.exam.audio import UPLOAD_NEW, UPLOAD_OVERWRITE, UPLOAD_SAME, md5_of, plan_uploads
    from apps.vocabulary.audio import BUCKET, parse_audio_name, public_audio_url
    from apps.vocabulary.models import ExampleSentence, Vocabulary

    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key:
        say(RED, "LỖI", "Thiếu SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY trong .env (xem .env.example).")
        sys.exit(1)
    say(YELLOW if args.apply else GREEN, "MODE", "GHI THẬT" if args.apply else "CHẠY THỬ (không ghi gì)")

    with connection.cursor() as c:
        cols = {col.name for col in connection.introspection.get_table_description(c, ExampleSentence._meta.db_table)}
    has_col = "audio_url" in cols
    if not has_col:
        say(RED if args.apply else YELLOW, "MIGRATE", "DB chưa có cột ExampleSentence.audio_url — chạy trước: "
            ".venv\\Scripts\\python.exe manage.py migrate --settings=config.settings.supabase")
        if args.apply:
            sys.exit(1)

    files = {p.name: p for p in sorted(args.folder.glob("*.mp3")) if parse_audio_name(p.name)}
    local = {name: md5_of(p) for name, p in files.items()}
    has_bucket = bucket_exists(base, key, BUCKET)
    remote = list_remote(base, key, BUCKET) if has_bucket else {}
    if not has_bucket:
        say(YELLOW, "BUCKET", f'"{BUCKET}" chưa có — --apply sẽ tạo (public).')
    plan, orphans = plan_uploads(local, remote)
    counts = {UPLOAD_NEW: 0, UPLOAD_OVERWRITE: 0, UPLOAD_SAME: 0}
    for _, action in plan:
        counts[action] += 1

    # URL mong muốn cho từng dòng DB; chỉ dòng đang khác mới ghi.
    want = {"w": {}, "e": {}}
    for name, md5 in local.items():
        kind, pk = parse_audio_name(name)
        want[kind][pk] = (name, public_audio_url(base, name, md5))
    models = {"w": Vocabulary, "e": ExampleSentence}
    changes = {}
    for kind, model in models.items():
        if kind == "e" and not has_col:  # chạy thử trước migrate: coi như câu nào cũng phải ghi
            current = dict.fromkeys(model.objects.filter(pk__in=want[kind]).values_list("pk", flat=True), "")
        else:
            current = dict(model.objects.filter(pk__in=want[kind]).values_list("pk", "audio_url"))
        changes[kind] = {pk: want[kind][pk] for pk, url in current.items() if url != want[kind][pk][1]}
    missing_rows = sum(len(want[k]) - models[k].objects.filter(pk__in=want[k]).count() for k in want)

    failed = []
    if args.apply:
        if not has_bucket:
            create_bucket(base, key, BUCKET)
            say(GREEN, "BUCKET", f'đã tạo "{BUCKET}" (public)')
        todo = [(n, a) for n, a in plan if a != UPLOAD_SAME]

        def run(item):
            name, action = item
            try:
                upload(base, key, BUCKET, name, files[name], overwrite=action == UPLOAD_OVERWRITE)
            except (urllib.error.URLError, OSError) as e:
                detail = e.read()[:200] if isinstance(e, urllib.error.HTTPError) else e
                return f"{name}: {detail!r}"

        with ThreadPoolExecutor(WORKERS) as pool:
            for i, err in enumerate(pool.map(run, todo), 1):
                if err:
                    failed.append(err)
                if i % 500 == 0:
                    say(DIM, "…", f"upload {i}/{len(todo)}")
        bad = {f.split(":", 1)[0] for f in failed}

        act_as(args.as_user)
        try:
            now, user = timezone.now(), get_current_user()
            with transaction.atomic():
                for kind, model in models.items():
                    objs = []
                    for pk, (name, url) in changes[kind].items():
                        if name in bad:  # file chưa lên bucket thì không trỏ URL tới nó
                            continue
                        obj = model(pk=pk, audio_url=url, updated_at=now)
                        obj.updated_by = user
                        objs.append(obj)
                    model.objects.bulk_update(objs, ["audio_url", "updated_at", "updated_by"], batch_size=500)
        finally:
            middleware._thread_locals.user = None

    print()
    print(f"  File trên máy : {len(local)}  ·  object trên bucket: {len(remote)}")
    print(f"  Upload mới    : {counts[UPLOAD_NEW]}")
    print(f"  Ghi đè        : {counts[UPLOAD_OVERWRITE]}")
    print(f"  Giữ nguyên    : {counts[UPLOAD_SAME]}")
    print(f"  Ghi audio_url : {len(changes['w'])} từ, {len(changes['e'])} câu ví dụ")
    if failed:
        print(f"{RED}  Lỗi upload    : {len(failed)} (các dòng này KHÔNG ghi audio_url){RESET}")
        for f in failed[:20]:
            print("     •", f)
    if missing_rows:
        print(f"{DIM}  File không còn dòng DB (từ/câu đã xoá): {missing_rows} — vẫn upload, không ghi URL{RESET}")
    if orphans:
        print(f"{DIM}  Object trên bucket không còn file trên máy (chỉ báo, không xoá): {len(orphans)}{RESET}")
    if not args.apply:
        print(f"\nChạy lại với {YELLOW}--apply --as-user dat{RESET} để ghi thật.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
