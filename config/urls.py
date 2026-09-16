from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("vocabulary/", include("apps.vocabulary.urls")),
    path("learning/", include("apps.learning.urls")),
    path("practice-sheets/", include("apps.practice_sheets.urls")),
    path("error-reports/", include("apps.error_reports.urls")),
    # "admin/" la Django admin (CRUD); "admin-panel/" la man tong quan SC07.
    path("admin-panel/", include("apps.admin_panel.urls")),
    path("", include("apps.learning.urls_home")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
