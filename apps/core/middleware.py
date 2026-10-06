"""
Makes the current request's user available inside model.save(), so
AuditableModel can auto-fill created_by / updated_by without every
view having to pass the user explicitly.
"""
import threading
import time

_thread_locals = threading.local()


def get_current_user():
    return getattr(_thread_locals, "user", None)


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.user = getattr(request, "user", None)
        try:
            response = self.get_response(request)
        finally:
            _thread_locals.user = None
        return response


class ServerTimingMiddleware:
    """Header `Server-Timing` cho mọi response (spec.md T4.3.0): tổng thời gian
    xử lý trong Django, thời gian chờ DB và số query — xem ngay ở Chrome
    DevTools > Network > Timing mà không cần công cụ đo riêng.

    Đặt ĐẦU danh sách MIDDLEWARE để đo cả session/auth (đọc session cũng là
    query). Tắt bằng biến môi trường SERVER_TIMING=false.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.db import connection

        stats = {"count": 0, "seconds": 0.0}

        def count_query(execute, sql, params, many, context):
            started = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                stats["count"] += 1
                stats["seconds"] += time.perf_counter() - started

        started = time.perf_counter()
        with connection.execute_wrapper(count_query):
            response = self.get_response(request)
        total_ms = (time.perf_counter() - started) * 1000
        response["Server-Timing"] = (
            f'app;dur={total_ms:.1f}, '
            f'db;dur={stats["seconds"] * 1000:.1f};desc="{stats["count"]} queries"'
        )
        return response
