"""
Settings cho môi trường Supabase.

    DJANGO_SETTINGS_MODULE=config.settings.supabase

Khác `prod.py` ở chỗ lấy thông tin database từ MỘT biến `DATABASE_URL` —
chuỗi copy thẳng từ Supabase Dashboard > Connect — thay vì 5 biến DB_* rời.
Lý do: Supabase phát ba kiểu connection string, và mỗi kiểu cần cấu hình
Django khác nhau:

    Direct        db.<ref>.supabase.co:5432          IPv6 mặc định
    Session       ...pooler.supabase.com:5432        IPv4, có prepared statement
    Transaction   ...pooler.supabase.com:6543        IPv4, KHÔNG prepared statement

Cổng 6543 (transaction mode) không giữ session giữa các câu lệnh, nên phải
tắt server-side cursor và không được giữ connection — nếu không Django sẽ ném
"prepared statement ... already exists". File này tự phát hiện theo cổng.

Khuyến nghị: chạy `migrate` qua Direct hoặc Session (5432); để Transaction
(6543) cho runtime serverless.
"""
import environ

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env  # noqa: F401

DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# --- Database ---------------------------------------------------------------
DATABASE_URL = env("DATABASE_URL")

_db = environ.Env.db_url_config(DATABASE_URL)
_db.setdefault("ENGINE", "django.db.backends.postgresql")

# Supabase bắt buộc TLS. `verify-full` chặt hơn nhưng cần CA bundle của
# Supabase trên máy chạy, nên mặc định để `require`.
_options = dict(_db.get("OPTIONS") or {})
_options.setdefault("sslmode", env("DB_SSLMODE", default="require"))
_options.setdefault("connect_timeout", env.int("DB_CONNECT_TIMEOUT", default=10))
_db["OPTIONS"] = _options

IS_TRANSACTION_POOLER = str(_db.get("PORT") or "") == "6543"

if IS_TRANSACTION_POOLER:
    _db["CONN_MAX_AGE"] = 0
    _db["DISABLE_SERVER_SIDE_CURSORS"] = True
else:
    _db["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
    _db["CONN_HEALTH_CHECKS"] = True

DATABASES = {"default": _db}

# --- Static -----------------------------------------------------------------
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- Bảo mật khi DEBUG=False ------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 7)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    X_FRAME_OPTIONS = "DENY"
