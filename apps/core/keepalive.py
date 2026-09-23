"""
Giữ web service Render (gói free) luôn thức bằng cách TỰ PING chính mình.

VÌ SAO: Render free cho instance ngủ sau ~15 phút không có request đi vào; người
dùng kế tiếp phải chờ ~30-60 giây để nó dậy. Một luồng nền gọi
https://<RENDER_EXTERNAL_HOSTNAME>/healthz/ theo chu kỳ < 15 phút. Request đi
ra Internet rồi vòng lại qua proxy của Render nên được tính là traffic đi vào.

GIỚI HẠN — đọc trước khi trông cậy vào nó:
- Chỉ GIỮ được server đang thức; không ĐÁNH THỨC được server đã ngủ (lúc ngủ thì
  luồng này cũng chết theo). Sau khi deploy, instance mới lên là luồng tự chạy.
- Render free có 750 giờ instance/tháng cho CẢ tài khoản. Một service chạy
  24/7 dùng ~720-744 giờ — vừa đủ cho MỘT service. Có thêm service free khác
  cũng bật keep-alive thì hết giờ trước cuối tháng và mọi service free bị dừng.

CÁCH CHẠY:
- start() được gọi từ config/wsgi.py — file này chỉ được nạp bởi gunicorn, nên
  `manage.py migrate/collectstatic/test` không bao giờ bật luồng.
- gunicorn chạy nhiều worker -> mỗi worker gọi start() một lần. Chỉ worker nào
  giữ được file lock (fcntl) mới ping; các worker khác thử lại mỗi phút, nên
  worker giữ lock bị gunicorn thay thế thì worker khác tự tiếp quản.
- Không có settings.KEEPALIVE_URL (máy dev) -> không làm gì.
- Bật/tắt, chu kỳ: đọc từ SiteSetting mỗi TICK_SECONDS giây — admin đổi ở màn
  Cài đặt hệ thống là có hiệu lực ngay, không cần deploy lại.
"""
import logging
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

TICK_SECONDS = 30
LOCK_RETRY_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = "bjt-goi-keepalive/1.0"
LOCK_PATH = os.path.join(tempfile.gettempdir(), "bjt-goi-keepalive.lock")

_started = False
_start_lock = threading.Lock()


def target_url():
    """URL sẽ ping, "" nếu môi trường này không cấu hình (máy dev)."""
    return getattr(settings, "KEEPALIVE_URL", "") or ""


def start():
    """Khởi động luồng nền — gọi nhiều lần cũng chỉ chạy một luồng/tiến trình."""
    global _started
    if not target_url():
        return
    with _start_lock:
        if _started:
            return
        _started = True
    thread = threading.Thread(target=_run, name="keepalive", daemon=True)
    thread.start()


def _acquire_process_lock():
    """Trả về file handle nếu tiến trình này giành được quyền ping, None nếu
    worker khác đang giữ. Windows không có fcntl -> luôn coi như giành được
    (Windows chỉ là máy dev, và máy dev không có KEEPALIVE_URL)."""
    try:
        import fcntl
    except ImportError:
        return open(os.devnull, "w")
    fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh  # giữ tham chiếu = giữ lock, tiến trình chết thì OS tự nhả


def _read_config():
    """(enabled, interval_minutes) từ DB. Lỗi DB -> None để vòng lặp bỏ qua tick."""
    from django.db import close_old_connections

    from apps.core.models import SiteSetting

    close_old_connections()
    try:
        cfg = SiteSetting.load()
        return cfg.keepalive_enabled, cfg.keepalive_interval_minutes
    except Exception:  # noqa: BLE001 — luồng nền không được chết vì DB chập chờn
        logger.exception("keepalive: không đọc được SiteSetting")
        return None
    finally:
        # Không giữ kết nối Supabase pooler suốt 30 giây ngủ giữa hai tick.
        close_old_connections()


def ping_once(url=None):
    """Gọi URL một lần. Trả về (ok, mô tả ngắn). Dùng chung cho luồng nền và
    nút "Ping thử ngay" ở màn Cài đặt hệ thống."""
    url = url or target_url()
    if not url:
        return False, "Chưa cấu hình KEEPALIVE_URL"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            elapsed = int((time.monotonic() - started) * 1000)
            return 200 <= resp.status < 400, f"HTTP {resp.status} · {elapsed} ms"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"[:255]


def record_result(ok, status):
    """Ghi kết quả lần ping gần nhất để admin xem. Dùng .update() để không đè
    updated_by/updated_at của admin."""
    from django.db import close_old_connections
    from django.utils import timezone

    from apps.core.models import SiteSetting

    try:
        SiteSetting.load()  # bảo đảm có dòng pk=1
        SiteSetting.objects.filter(pk=SiteSetting.SINGLETON_PK).update(
            keepalive_last_ping_at=timezone.now(),
            keepalive_last_status=status[:255],
            keepalive_last_ok=ok,
        )
    except Exception:  # noqa: BLE001
        logger.exception("keepalive: không ghi được kết quả ping")
    finally:
        close_old_connections()


def _run():
    lock_fh = None
    last_ping = time.monotonic()  # lần ping đầu = sau đúng một chu kỳ
    while True:
        try:
            if lock_fh is None:
                lock_fh = _acquire_process_lock()
                if lock_fh is None:
                    time.sleep(LOCK_RETRY_SECONDS)
                    continue
                logger.info("keepalive: tiến trình %s nhận nhiệm vụ ping %s", os.getpid(), target_url())

            cfg = _read_config()
            if cfg is not None:
                enabled, minutes = cfg
                if enabled and time.monotonic() - last_ping >= minutes * 60:
                    ok, status = ping_once()
                    last_ping = time.monotonic()
                    record_result(ok, status)
                    log = logger.info if ok else logger.warning
                    log("keepalive: %s", status)
                elif not enabled:
                    # Tắt rồi bật lại -> đếm lại từ lúc bật, không ping dồn ngay.
                    last_ping = time.monotonic()
        except Exception:  # noqa: BLE001
            logger.exception("keepalive: lỗi không mong đợi, thử lại tick sau")
        time.sleep(TICK_SECONDS)
