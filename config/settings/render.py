"""
Settings khi chạy trên Render (web service) — database vẫn là Supabase.

    DJANGO_SETTINGS_MODULE=config.settings.render

File này CHỈ thêm phần riêng của Render lên trên `supabase.py`; toàn bộ cấu
hình database, static (WhiteNoise) và bảo mật kế thừa nguyên từ đó.

Vì sao tách khỏi `supabase.py`: Supabase là *database*, Render là *nơi chạy
app* — hai thứ độc lập. Mai kia đổi sang Fly.io/Railway thì chỉ cần một file
tương tự cạnh file này, `supabase.py` không phải đụng tới.
"""
import os

from .supabase import *  # noqa: F401,F403
from .supabase import ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS

# Render tự đặt biến này bằng hostname thật của service, vd
# "bjt-goi.onrender.com". Đọc từ đó thay vì hardcode tên service để đổi tên
# service hay dựng thêm môi trường preview đều không phải sửa code.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")

if RENDER_EXTERNAL_HOSTNAME:
    if RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
        ALLOWED_HOSTS = [*ALLOWED_HOSTS, RENDER_EXTERNAL_HOSTNAME]
    # Django 4+ bắt buộc origin có scheme. Thiếu dòng này thì mọi form POST
    # (đăng nhập, đăng ký) trả 403 CSRF verification failed.
    _origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if _origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS = [*CSRF_TRUSTED_ORIGINS, _origin]

# Đích tự ping giữ server free thức (apps/core/keepalive.py). Có thể ghi đè
# bằng biến môi trường KEEPALIVE_URL; đặt KEEPALIVE_URL="" để tắt hẳn ở mức
# hạ tầng (khi đó bật/tắt trên màn quản trị không còn tác dụng).
KEEPALIVE_URL = os.environ.get(
    "KEEPALIVE_URL",
    f"https://{RENDER_EXTERNAL_HOSTNAME}/healthz/" if RENDER_EXTERNAL_HOSTNAME else "",
)

# Render gom stdout/stderr vào tab Logs — ghi thẳng ra đó, không ghi ra file
# vì đĩa của instance là tạm, mất sạch sau mỗi lần deploy.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{levelname}] {asctime} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    "loggers": {
        # Mặc định Django nuốt traceback của lỗi 500 khi DEBUG=False; bật lên
        # để còn đọc được nguyên nhân trong Logs.
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
