import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
application = get_wsgi_application()

# Luồng nền tự ping giữ Render free thức. Đặt ở ĐÂY (chứ không ở AppConfig.ready)
# vì wsgi.py chỉ được gunicorn nạp — manage.py migrate/test không bật luồng.
# Không có settings.KEEPALIVE_URL thì start() không làm gì.
from apps.core import keepalive  # noqa: E402

keepalive.start()
