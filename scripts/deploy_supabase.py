"""
Deploy schema BJT-GOI lên Supabase.

Script này KHÔNG chứa bí mật nào. Mọi thông tin kết nối đọc từ file `.env` ở
gốc repo (hoặc từ biến môi trường). Xem `.env.example`.

    # 1. kiểm tra kết nối + xem sẽ chạy migration nào, KHÔNG ghi gì
    python scripts/deploy_supabase.py --check

    # 2. deploy thật
    python scripts/deploy_supabase.py --apply

    # 2b. chỉ tạo tài khoản khi DB đã migrate rồi
    python scripts/deploy_supabase.py --apply --seed-users --yes

    # 3. kèm tạo superuser và gom static
    python scripts/deploy_supabase.py --apply --superuser --collectstatic

Các bước khi --apply:
    1. Đọc và che DATABASE_URL, nhận diện kiểu kết nối (direct / session / transaction)
    2. Thử kết nối, in phiên bản PostgreSQL và địa chỉ server
    3. Liệt kê bảng đang có trong schema public (DB trống hay không)
    4. `migrate`
    5. `seed_mastercode`  (bắt buộc — thiếu là mọi <select> trên UI rỗng)
    6. `seed_users`                  (chỉ khi --seed-users)
    6. `createsuperuser --noinput`   (chỉ khi --superuser)
    7. `collectstatic --noinput`     (chỉ khi --collectstatic)
    8. Hậu kiểm: mọi bảng của dự án phải có đủ 4 cột audit

Script dừng ngay khi một bước lỗi, và không bước nào ở --check ghi vào DB.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

LOCAL_APPS = ["accounts", "core", "vocabulary", "learning", "practice_sheets", "gamification"]
AUDIT_COLUMNS = {"created_at", "created_by_id", "updated_at", "updated_by_id"}

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    GREEN = RED = YELLOW = DIM = RESET = ""


def ok(msg):
    print(f"{GREEN}  OK  {RESET}{msg}")


def warn(msg):
    print(f"{YELLOW} CẢNH BÁO {RESET}{msg}")


def fail(msg):
    print(f"{RED} LỖI {RESET}{msg}")
    sys.exit(1)


def step(n, msg):
    print(f"\n{DIM}[{n}]{RESET} {msg}")


def mask(url: str) -> str:
    """Che mật khẩu trong connection string trước khi in ra màn hình/log."""
    parts = urlsplit(url)
    if parts.password:
        netloc = parts.netloc.replace(f":{parts.password}@", ":********@")
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return url


def describe_mode(url: str) -> tuple[str, str]:
    """Nhận diện kiểu kết nối Supabase từ host/port."""
    p = urlsplit(url)
    host, port = (p.hostname or ""), str(p.port or 5432)
    if "pooler.supabase.com" in host and port == "6543":
        return "transaction", (
            "Transaction pooler (6543) — KHÔNG hỗ trợ prepared statement.\n"
            "           Django đã tự tắt server-side cursor, nhưng để chạy migrate\n"
            "           nên dùng Session pooler (5432) hoặc Direct cho chắc."
        )
    if "pooler.supabase.com" in host:
        return "session", "Session pooler (5432) — IPv4, hỗ trợ prepared statement. Hợp để migrate."
    if host.startswith("db.") and host.endswith(".supabase.co"):
        return "direct", (
            "Direct connection — Supabase trả IPv6 mặc định.\n"
            "           Mạng nhà/công ty không có IPv6 sẽ báo 'Network is unreachable';\n"
            "           khi đó đổi sang Session pooler trong Dashboard > Connect."
        )
    return "khác", f"Host không theo mẫu Supabase ({host}) — vẫn chạy bình thường nếu kết nối được."


def main() -> None:
    ap = argparse.ArgumentParser(description="Deploy schema BJT-GOI lên Supabase.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="Chỉ kiểm tra, không ghi gì vào DB.")
    g.add_argument("--apply", action="store_true", help="Chạy migrate + seed thật.")
    ap.add_argument("--seed-users", action="store_true",
                    help="Chạy luôn `manage.py seed_users` (1 admin + 2 người dùng).")
    ap.add_argument("--superuser", action="store_true",
                    help="Tạo superuser từ DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD.")
    ap.add_argument("--collectstatic", action="store_true", help="Chạy collectstatic --noinput.")
    ap.add_argument("--yes", action="store_true", help="Không hỏi xác nhận khi DB đã có bảng.")
    args = ap.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.supabase")

    # --- 1. Cấu hình ---------------------------------------------------------
    step(1, "Đọc cấu hình")
    try:
        import environ
    except ImportError:
        fail("Thiếu django-environ. Chạy: pip install -r requirements.txt")

    env = environ.Env()
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        environ.Env.read_env(env_file)
        ok(f".env: {env_file}")
    else:
        warn(f"Không thấy {env_file} — dùng biến môi trường của shell.")

    missing = [k for k in ("DATABASE_URL", "SECRET_KEY") if not os.environ.get(k)]
    if missing:
        fail("Thiếu biến bắt buộc: " + ", ".join(missing) + ". Xem .env.example.")

    url = os.environ["DATABASE_URL"]
    ok(f"DATABASE_URL: {mask(url)}")
    if not os.environ.get("ALLOWED_HOSTS"):
        warn("ALLOWED_HOSTS trống — chỉ ảnh hưởng lúc chạy web, không ảnh hưởng migrate.")

    mode, note = describe_mode(url)
    ok(f"Kiểu kết nối: {mode}")
    print(f"       {DIM}{note}{RESET}")
    if mode == "transaction" and args.apply:
        warn("Đang migrate qua transaction pooler. Nếu lỗi prepared statement, đổi sang cổng 5432.")

    # --- 2. Kết nối ----------------------------------------------------------
    step(2, "Thử kết nối")
    import django

    django.setup()
    from django.db import connection

    try:
        with connection.cursor() as c:
            c.execute("select version(), current_database(), current_user, "
                      "coalesce(host(inet_server_addr()), 'unix-socket')")
            version, dbname, dbuser, addr = c.fetchone()
    except Exception as exc:  # noqa: BLE001 — muốn in gọn cho người dùng
        fail(f"Không kết nối được: {type(exc).__name__}: {exc}")

    ok(version.split(" on ")[0])
    ok(f"database={dbname}  user={dbuser}  server={addr}")

    # --- 3. Trạng thái hiện tại ---------------------------------------------
    step(3, "Kiểm tra schema public")
    with connection.cursor() as c:
        c.execute("select tablename from pg_tables where schemaname='public' order by 1")
        existing = [r[0] for r in c.fetchall()]
    if existing:
        warn(f"Đã có {len(existing)} bảng: {', '.join(existing[:6])}"
             + (" ..." if len(existing) > 6 else ""))
    else:
        ok("Schema public đang trống — đây là lần deploy đầu tiên.")

    from django.core.management import call_command

    print()
    call_command("showmigrations", "--list", *LOCAL_APPS)

    if args.check:
        print(f"\n{GREEN}--check xong. Không có gì được ghi vào database.{RESET}")
        print("Chạy lại với --apply để deploy thật.")
        return

    if existing and not args.yes:
        ans = input("\nDatabase đã có bảng. Tiếp tục migrate? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("Đã huỷ.")
            return

    # --- 4-7. Deploy ---------------------------------------------------------
    step(4, "migrate")
    call_command("migrate", "--noinput")
    ok("migrate xong")

    step(5, "seed_mastercode")
    call_command("seed_mastercode")
    ok("seed xong")

    if args.seed_users:
        step(6, "seed_users")
        call_command("seed_users")
        ok("seed_users xong")

    if args.superuser:
        step(6, "createsuperuser")
        need = ["DJANGO_SUPERUSER_USERNAME", "DJANGO_SUPERUSER_PASSWORD"]
        if any(not os.environ.get(k) for k in need):
            fail("Cần " + " và ".join(need) + " trong .env để tạo superuser không tương tác.")
        from django.contrib.auth import get_user_model

        username = os.environ["DJANGO_SUPERUSER_USERNAME"]
        if get_user_model().objects.filter(username=username).exists():
            warn(f"User '{username}' đã tồn tại — bỏ qua.")
        else:
            call_command("createsuperuser", "--noinput")
            ok(f"đã tạo superuser '{username}'")

    if args.collectstatic:
        step(7, "collectstatic")
        call_command("collectstatic", "--noinput", verbosity=0)
        ok("collectstatic xong")

    # --- 8. Hậu kiểm ---------------------------------------------------------
    step(8, "Hậu kiểm")
    from django.apps import apps as django_apps

    tables = sorted(
        m._meta.db_table for m in django_apps.get_models()
        if m._meta.app_label in LOCAL_APPS
    )
    missing_audit = []
    with connection.cursor() as c:
        for t in tables:
            c.execute(
                "select column_name from information_schema.columns "
                "where table_schema='public' and table_name=%s", [t]
            )
            cols = {r[0] for r in c.fetchall()}
            if not cols:
                missing_audit.append((t, "BẢNG KHÔNG TỒN TẠI"))
            elif AUDIT_COLUMNS - cols:
                missing_audit.append((t, "thiếu " + ", ".join(sorted(AUDIT_COLUMNS - cols))))

    if missing_audit:
        for t, why in missing_audit:
            print(f"  {RED}x{RESET} {t}: {why}")
        fail(f"{len(missing_audit)}/{len(tables)} bảng chưa đạt.")
    ok(f"{len(tables)}/{len(tables)} bảng của dự án có đủ 4 cột audit")

    from apps.core.models import MasterCode

    n = MasterCode.objects.count()
    (ok if n else fail)(f"core_mastercode: {n} dòng")

    print(f"\n{GREEN}Deploy xong.{RESET} Bước tiếp theo: trỏ app vào "
          "DJANGO_SETTINGS_MODULE=config.settings.supabase và chạy gunicorn.")


if __name__ == "__main__":
    main()
