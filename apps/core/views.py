"""View dùng chung toàn hệ thống, không thuộc feature nào."""
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods


@never_cache
@require_http_methods(["GET", "HEAD"])
def healthz_view(request):
    """Health check của Render (`healthCheckPath` trong render.yaml) và đích
    cho cron ping từ bên ngoài (spec.md T4.1). CỐ Ý không đụng DB và không cần
    đăng nhập: chỉ cần request đi vào tới server là Render tính là có traffic."""
    return HttpResponse("ok", content_type="text/plain")
